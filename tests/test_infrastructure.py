from concurrent.futures import ThreadPoolExecutor

import pytest

from chemlab.adapters.models import ModelService
from chemlab.application import Application
from chemlab.records import Corpus, PrecedentSource, canonical_bytes, digest
from chemlab.reporting.bundles import publish, read_bundle
from chemlab.store import IntegrityError
from chemlab.verification import verify


def test_corrupt_artifact_is_never_a_cache_hit(lab):
    store, _, _, service, _ = lab
    ref, _ = service.backward("CCOC(C)=O", 10)
    (store.objects / f"{ref}.json").write_bytes(b"{}")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        service.backward("CCOC(C)=O", 10)


def test_simultaneous_identical_requests_execute_once(lab):
    store, config, *_ = lab
    services = [ModelService(store, config.backward_manifest) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda service: service.backward("CCOC(C)=O", 10), services))
    assert len({ref for ref, _ in results}) == 1
    assert sum(service.actual_inferences for service in services) == 1
    assert sum(service.cache_hits for service in services) == 3


def test_bundle_reports_and_files_are_bound(lab, ester_route):
    store, config, _, _, forward = lab
    report = verify(store, ester_route.model_dump(mode="json"), "CCOC(C)=O", config, forward)
    path = publish(
        store,
        "test-complete",
        {"config_ref": store.put("run_config", config)},
        [(ester_route, report)],
    )
    bundle = read_bundle(path)
    assert bundle["state"] == "complete"
    assert len(bundle["groups"]["verified_consistent"]) == 1
    ref = next(iter(bundle["files"].values()))
    (path / "objects" / f"{ref}.json").write_bytes(b"{}")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        read_bundle(path)


def test_report_for_another_route_cannot_publish(lab, ester_route):
    store, config, *_ = lab
    report = verify(store, ester_route.model_dump(mode="json"), "CCOC(C)=O", config)
    changed = ester_route.model_copy(update={"search_cost": 123.0})
    with pytest.raises(IntegrityError, match="different route"):
        publish(store, "mismatch", {}, [(changed, report)])
    assert not (store.root / "bundles" / "mismatch").exists()


def test_interrupted_bundle_never_reads_as_complete(lab, monkeypatch, ester_route):
    import chemlab.reporting.bundles as bundles

    store, config, *_ = lab
    report = verify(store, ester_route.model_dump(mode="json"), "CCOC(C)=O", config)

    def interrupt(*args):
        raise OSError("simulated interrupted publication")

    monkeypatch.setattr(bundles.os, "rename", interrupt)
    with pytest.raises(OSError):
        publish(store, "interrupted", {}, [(ester_route, report)])
    assert not (store.root / "bundles" / "interrupted").exists()
    staging = next((store.root / "bundles").glob(".staging-*"))
    with pytest.raises(IntegrityError):
        read_bundle(staging)


def test_complete_application_and_exact_report_replay(lab):
    store, config, *_ = lab
    application = Application(store)
    run_id = application.prepare("CCOC(C)=O", config)
    application.execute(run_id)
    row = application.run(run_id)
    assert row["state"] == "complete", row["error"]
    bundle = row["result"]
    manifest = bundle["objects"][bundle["run_ref"]]["payload"]
    assert manifest["forward_statistics"] == {"actual_inferences": 1, "cache_hits": 0}
    item = bundle["groups"]["verified_consistent"][0]
    raw_route = bundle["objects"][item["route_ref"]]["payload"]
    old_report = bundle["objects"][item["report_ref"]]["payload"]
    new_report = verify(
        store, raw_route, row["target"], config, application.model(config.forward_manifest)
    )
    assert canonical_bytes(new_report) == canonical_bytes(old_report)


def test_final_reference_cannot_supply_evidence(lab):
    store, config, *_ = lab
    corpus = Corpus(
        name="held out",
        version="1",
        partition="final_reference",
        source="test",
        license="test",
        multiplicity="unique",
        records=(PrecedentSource(source_id="r1", product="CC", precursors=("C",)),),
    )
    ref = store.put("corpus", corpus)
    with pytest.raises(ValueError, match="Final-reference"):
        Application(store).prepare("CC", config.model_copy(update={"corpus_ref": ref}))


def test_hash_is_stable_for_dictionary_order():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
