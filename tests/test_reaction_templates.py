import sqlite3

import pytest

from chemlab.evidence.chemical_checks import assess_reaction
from chemlab.evidence.reaction_library import HEADER, ReactionLibrary, build_library, file_digest
from chemlab.evidence.reaction_templates import (
    ContextLibrary,
    build_context_library,
    extract_context,
    replay_context,
)
from chemlab.store import IntegrityError

MAPPED = "[CH3:1][CH2:2][CH2:3][OH:4]>>[CH3:1][CH2:2][CH:3]=[O:4]"
ANALOG = "[CH3:1][CH2:2][CH2:3][CH2:4][OH:5]>>[CH3:1][CH2:2][CH2:3][CH:4]=[O:5]"
SMARTS = "[C:1]-[CH;D2;+0:2]=[O;H0;D1;+0:3]>>[C:1]-[CH2;D2;+0:2]-[OH;D1;+0:3]"


@pytest.fixture
def libraries(tmp_path):
    path = tmp_path / "source.rsmi"
    path.write_text(HEADER + "\n" + MAPPED + "\tUS-fixture\t1\t2000\n")
    root = tmp_path / "source-index"
    build_library(
        [
            {
                "id": "software-contract-fixture",
                "path": str(path),
                "sha256": file_digest(path),
                "kind": "reported_patent",
                "partition": "training",
            }
        ],
        root,
    )
    source = ReactionLibrary(root, file_digest(root / "manifest.json"))
    target = tmp_path / "context-index"
    build_context_library(source, target)
    return source, ContextLibrary(target, file_digest(target / "manifest.json"), source)


def test_public_extractor_and_replay_are_bound_to_precursor_identity():
    context = extract_context(MAPPED, "CCC=O", ("CCCO",))
    assert context["status"] == "observed"
    assert context["template"]["reaction_smarts"] == SMARTS
    assert replay_context(context["template"], "CCCC=O", ("CCCCO",))["status"] == "pass"
    assert replay_context(context["template"], "CCCC=O", ("CCCO",))["status"] == "unknown"
    assert replay_context(context["template"], "CCCC=O", ("CCCCO", "CCCCO"))["status"] == "unknown"
    assert extract_context(MAPPED, "CC=O", ("CCO",))["status"] == "unknown"
    assert extract_context("CCO>>CC=O", "CC=O", ("CCO",))["status"] == "unknown"


def test_replay_enumeration_has_stable_order_and_preserves_duplicate_outputs(monkeypatch):
    from chemlab.evidence import reaction_templates as module

    monkeypatch.setattr(module, "rdchiralRunText", lambda *a, **kw: ["O.CC", "CO.C", "CO.C"])
    result = module._replay_context({"reaction_smarts": "software-fixture"}, "CCO", ("CO", "C"))
    assert result["status"] == "pass"
    assert result["outputs"] == [["C", "CO"], ["C", "CO"], ["CC", "O"]]


def test_source_context_support_keeps_scope_and_excludes_final_sources(libraries):
    sources, contexts = libraries
    exact = sources.lookup("CCC=O", ("CCCO",))
    assert exact["status"] == "reported_match"
    assert sources.lookup("CCCC=O", ("CCCCO",))["status"] == "unknown"
    result = contexts.lookup(ANALOG, "CCCC=O", ("CCCCO",))
    assert result["status"] == "context_replay_match"
    assert result["chemical_feasibility"] == "unresolved"
    assert result["matches"][0]["reference"] == "https://patents.google.com/patent/US-fixture"
    from chemlab.records import digest

    # Excluding this query's exact source identity must still permit another source's analogy.
    query_key = digest({"product": "CCCC=O", "precursors": ["CCCCO"]})
    assert (
        contexts.lookup(ANALOG, "CCCC=O", ("CCCCO",), excluded=frozenset({query_key}))["status"]
        == "context_replay_match"
    )
    key = exact["matches"][0]["record"]["key"]
    excluded = contexts.lookup(ANALOG, "CCCC=O", ("CCCCO",), excluded=frozenset({key}))
    assert excluded["status"] == "unknown"
    assert excluded["matches"] == []
    assert excluded["excluded_sources"] == 1
    supported = assess_reaction("CCC=O", ("CCCO",), library=sources)
    assert supported["evidence_outcome"] == "support"
    assert supported["chemical_feasibility"] == "unresolved"


def test_context_and_source_batch_sessions_replay_and_detect_changes(libraries):
    source, contexts = libraries
    direct = contexts.lookup(ANALOG, "CCCC=O", ("CCCCO",))
    with source.session() as snapshot:
        assert snapshot.lookup("CCC=O", ("CCCO",)) == source.lookup("CCC=O", ("CCCO",))
    with contexts.session() as snapshot:
        assert snapshot.lookup(ANALOG, "CCCC=O", ("CCCCO",)) == direct
    with sqlite3.connect(contexts.database) as conn:
        conn.execute("UPDATE contexts SET payload='{}'")
    with pytest.raises(IntegrityError, match="changed"):
        contexts.lookup(ANALOG, "CCCC=O", ("CCCCO",))


def test_batch_does_not_return_a_publishable_success_after_source_changes(libraries):
    source, _ = libraries
    with pytest.raises(IntegrityError, match="during evidence batch"):
        with source.session() as snapshot:
            assert snapshot.lookup("CCC=O", ("CCCO",))["status"] == "reported_match"
            # Direct file damage simulates external corruption, not a SQLite writer.
            with source.database.open("ab") as stream:
                stream.write(b"damage")


def test_extraction_cache_preserves_exact_inputs_results_and_retry_of_errors(monkeypatch):
    from chemlab.evaluation import context_replay as experiment
    from chemlab.evidence import reaction_templates as module

    experiment.observed_context.cache_clear()
    original = module.extract_context
    calls = []

    def observed(*args):
        calls.append(args)
        if len(calls) == 1:
            return {"status": "error", "reason": "seeded transient extraction failure"}
        return original(*args)

    monkeypatch.setattr(experiment, "extract_context", observed)
    assert experiment.replay_context(MAPPED, "CCC=O", ("CCCO",))["status"] == "error"
    result = experiment.replay_context(MAPPED, "CCC=O", ("CCCO",))
    assert result["status"] == "observed"
    result["template"]["reaction_smarts"] = "caller corruption"
    assert (
        experiment.replay_context(MAPPED, "CCC=O", ("CCCO",))["template"]["reaction_smarts"]
        == SMARTS
    )
    assert len(calls) == 2
    assert experiment.replay_context(MAPPED, "CC=O", ("CCO",))["status"] == "unknown"
    experiment.observed_context.cache_clear()


def test_cli_context_evidence_replays_saved_maps_and_returns_nonzero_for_changed_findings(
    libraries, tmp_path
):
    import json
    import subprocess
    import sys

    from chemlab.evidence.chemical_service import KnowledgeConfig, register_knowledge
    from chemlab.store import Store

    source, contexts = libraries
    manifest = tmp_path / "fixture-mapper.json"
    manifest.write_text('{"provider":"software-contract-fixture"}')
    worker = tmp_path / "fixture-worker.py"
    worker.write_text(
        "import json,sys\nfrom chemlab.records import digest\n"
        "q=json.load(open(sys.argv[1]))\nm=json.load(open(sys.argv[4]))\n"
        f"mapped={ANALOG!r}\n"
        "raw={'provider_manifest':m,'provider_ref':digest(m),'results':["
        "{'input':r,'input_key':digest(r),'status':'ok',"
        "'raw_prediction':{'mapped_rxn':mapped}} for r in q]}\n"
        "json.dump(raw,open(sys.argv[2],'w'))\n"
    )
    store = Store(tmp_path / "cli-store")
    config = KnowledgeConfig(
        name="Software boundary fixture",
        source_path=str(source.root),
        source_manifest=source.manifest_ref,
        context_path=str(contexts.database.parent),
        context_manifest=contexts.manifest_ref,
        mapper_command=(sys.executable, str(worker)),
        mapper_manifest_path=str(manifest),
        mapper_manifest_hash=file_digest(manifest),
    )
    register_knowledge(store, "unit", config)
    command = [sys.executable, "-m", "chemlab", "--store", str(store.root)]
    checked = subprocess.run(
        [*command, "check-reaction", "CCCCO>>CCCC=O", "--knowledge", "unit"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert checked.returncode == 0, checked.stderr
    job = json.loads(checked.stdout)
    assert job["state"] == "complete", job
    assessment = next(iter(job["result"]["results"].values()))
    assert assessment["checks"]["context_precedent"]["status"] == "context_replay_match"
    assert assessment["chemical_feasibility"] == "unresolved"
    replay = subprocess.run(
        [*command, "replay-chemical-check", job["id"]], capture_output=True, text=True, timeout=60
    )
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["equivalent"] is True
    changed = store.get(job["result_ref"], "chemical_report")
    next(iter(changed["results"].values()))["checks"]["exact_precedent"]["reason"] = (
        "seeded wrong claim"
    )
    wrong_ref = store.put("chemical_report", changed)
    with store.connect() as conn:
        conn.execute("UPDATE chemical_jobs SET result_ref=? WHERE id=?", (wrong_ref, job["id"]))
    failed = subprocess.run(
        [*command, "replay-chemical-check", job["id"]], capture_output=True, text=True, timeout=60
    )
    assert failed.returncode == 1, failed.stderr
    assert json.loads(failed.stdout)["equivalent"] is False
