import sys

import pytest
from fastapi.testclient import TestClient

from chemlab.api import create_app
from chemlab.application import Application
from chemlab.evidence.chemical_service import (
    ChemicalService,
    KnowledgeConfig,
    mapping_batch,
    parse_reaction,
    route_queries,
)
from chemlab.evidence.reaction_library import file_digest
from chemlab.records import digest
from chemlab.reporting.chemical_exports import evidence_chemistry_zip, evidence_pdf
from chemlab.store import IntegrityError, Store


def test_job_publication_and_standalone_input_contract(tmp_path):
    service = ChemicalService(Store(tmp_path))
    query = parse_reaction("C>>CN")
    job_id = service.prepare([query], None)
    assert service.job(job_id)["state"] == "queued"
    with pytest.raises(ValueError, match="published"):
        evidence_pdf(service.job(job_id))
    service.execute(job_id)
    result = service.job(job_id)
    assert result["state"] == "complete"
    assert result["result"]["counts"] == {"contradiction": 1}
    assert result["result"]["chemical_feasibility"] == "unresolved"
    assert result["result"]["mapping_batch_ref"] is None
    assert result["progress"] == {"stage": "complete", "completed": 1, "total": 1}
    replayed = service.replay(job_id)
    assert replayed["equivalent"] is True
    assert replayed["fresh_model_inference"] is False
    with pytest.raises(ValueError, match="not queued"):
        service.execute(job_id)
    for invalid in ("CCO>O>CC=O", "CCO", "C>>*", ">>C"):
        with pytest.raises(ValueError):
            parse_reaction(invalid)


def test_mapping_raw_output_is_saved_before_invalid_bindings_are_rejected(tmp_path):
    store = Store(tmp_path / "store")
    manifest = tmp_path / "mapper.json"
    manifest.write_text('{"provider":"contract-fixture"}')
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import sys,json\n"
        "m=json.load(open(sys.argv[4]))\n"
        "json.dump({'provider_manifest':m,'provider_ref':'bad','results':[]},open(sys.argv[2],'w'))\n"
    )
    config = KnowledgeConfig(
        name="Fixture worker",
        mapper_command=(sys.executable, str(worker)),
        mapper_manifest_path=str(manifest),
        mapper_manifest_hash=file_digest(manifest),
    )
    with pytest.raises(IntegrityError, match="provider binding"):
        mapping_batch(store, [parse_reaction("CCO>>CC=O")], config)
    with store.connect() as conn:
        refs = conn.execute("SELECT ref FROM artifacts WHERE kind='mapping_batch'").fetchall()
    assert len(refs) == 1
    raw = store.get(refs[0][0], "mapping_batch")
    assert raw["raw_output"]["provider_ref"] == "bad"


def test_worker_failure_never_becomes_a_valid_map(tmp_path):
    store = Store(tmp_path / "store")
    manifest = tmp_path / "mapper.json"
    manifest.write_text('{"provider":"contract-fixture"}')
    config = KnowledgeConfig(
        name="Failed worker",
        mapper_command=(sys.executable, "-c", "exit(2)"),
        mapper_manifest_path=str(manifest),
        mapper_manifest_hash=file_digest(manifest),
    )
    ref, mappings = mapping_batch(store, [parse_reaction("CCO>>CC=O")], config)
    assert ref
    assert next(iter(mappings.values()))["status"] == "error"


def test_route_jobs_keep_every_selected_step_and_original_binding(lab):
    store, config, *_ = lab
    app = Application(store)
    run_id = app.prepare("CCOC(C)=O", config)
    app.execute(run_id)
    bundle = app.run(run_id)["result"]
    route_ref = bundle["groups"]["verified_consistent"][0]["route_ref"]
    queries, binding = route_queries(bundle, route_ref)
    assert len(queries) == len(binding["steps"]) == 1
    assert queries == [{"product": "CCOC(C)=O", "precursors": ["CCO", "CC(=O)O"]}]
    assert binding["steps"][0]["candidate_index"] == 0
    service = ChemicalService(store)
    job = service.prepare(queries, None, route_binding=binding)
    service.execute(job)
    report = service.job(job)["result"]
    assert report["route_binding"] == binding
    assert report["counts"] == {"unresolved": 1}
    assert report["route_summary"]["step_findings"] == {"unresolved": 1}
    assert report["route_summary"]["chemical_feasibility"] == "unresolved"
    assert app.run(run_id)["result"] == bundle


def test_evidence_pdf_and_editable_files_keep_bindings_and_uncertainty(tmp_path):
    import io
    import zipfile

    from pypdf import PdfReader
    from rdkit import Chem
    from rdkit.Chem import rdChemReactions

    service = ChemicalService(Store(tmp_path))
    query = parse_reaction("C[C@H](O)F.C[C@H](O)F.[13CH3]O.[Na+]>>C[C@H](O)F")
    job_id = service.prepare([query], None)
    service.execute(job_id)
    job = service.job(job_id)
    pdf = evidence_pdf(job)
    assert pdf == evidence_pdf(job)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Experimental feasibility remains unresolved" in text
    assert job["result_ref"] in text
    package = evidence_chemistry_zip(job)
    assert package == evidence_chemistry_zip(job)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert "molecules.sdf" in archive.namelist()
        mols = list(
            Chem.ForwardSDMolSupplier(io.BytesIO(archive.read("molecules.sdf")), removeHs=False)
        )
        assert len(mols) == 5
        identities = [Chem.MolToSmiles(m, isomericSmiles=True) for m in mols]
        assert identities.count("C[C@H](O)F") == 3
        assert identities.count("[13CH3]O") == identities.count("[Na+]") == 1
        reaction = rdChemReactions.ReactionFromRxnBlock(
            archive.read("reactions/reaction-0001.rxn").decode(),
            sanitize=True,
            removeHs=False,
        )
        assert reaction.GetNumReactantTemplates() == 4
    job["result"]["results"][digest(query)]["input"]["product"] = "C[C@@H](O)F"
    with pytest.raises(IntegrityError, match="binding"):
        evidence_chemistry_zip(job)


def test_api_chemical_jobs_export_only_completed_records(tmp_path):
    import time

    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/reactions/check", json={"reaction_smiles": "C>>CN"})
        assert response.status_code == 202
        job_id = response.json()["id"]
        for _ in range(200):
            job = client.get(f"/api/chemical-jobs/{job_id}").json()
            if job["state"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        assert job["state"] == "complete", job
        export = client.get(f"/api/chemical-jobs/{job_id}/report.json").json()
        for ref, envelope in export["objects"].items():
            assert digest(envelope) == ref
        assert client.get(f"/api/chemical-jobs/{job_id}/report.pdf").content.startswith(b"%PDF")
        assert client.get(f"/api/chemical-jobs/{job_id}/chemistry.zip").content.startswith(b"PK")
        assert client.get("/api/chemical-jobs/missing").status_code == 404
        assert (
            client.post("/api/reactions/check", json={"reaction_smiles": "C>O>C"}).status_code
            == 400
        )


def test_interrupted_jobs_stay_errors_on_restart(tmp_path):
    service = ChemicalService(Store(tmp_path))
    job_id = service.prepare([parse_reaction("CCO>>CC=O")], None)
    with TestClient(create_app(tmp_path)) as client:
        job = client.get(f"/api/chemical-jobs/{job_id}").json()
        assert job["state"] == "error"
        assert job["result"] is None
        assert client.get(f"/api/chemical-jobs/{job_id}/report.json").status_code == 409
        assert client.get(f"/api/chemical-jobs/{job_id}/report.pdf").status_code == 409
        assert client.get(f"/api/chemical-jobs/{job_id}/chemistry.zip").status_code == 409


def test_job_cannot_publish_another_requests_unchanged_report(tmp_path):
    store = Store(tmp_path)
    service = ChemicalService(store)
    first = service.prepare([parse_reaction("C>>CN")], None)
    second = service.prepare([parse_reaction("CCO>>CC=O")], None)
    service.execute(first)
    service.execute(second)
    ref = service.job(first)["result_ref"]
    with store.connect() as conn:
        conn.execute("UPDATE chemical_jobs SET result_ref=? WHERE id=?", (ref, second))
    with pytest.raises(IntegrityError, match="another request"):
        service.job(second)


def test_policy_change_after_submission_cannot_publish_a_completed_job(tmp_path, monkeypatch):
    from chemlab.evidence.chemical_checks import POLICY

    service = ChemicalService(Store(tmp_path))
    job_id = service.prepare([parse_reaction("CCO>>CC=O")], None)
    monkeypatch.setitem(POLICY, "version", "seeded policy change")
    service.execute(job_id)
    job = service.job(job_id)
    assert job["state"] == "error"
    assert job["result_ref"] is None
    assert "policy changed" in job["error"]


def test_route_evidence_never_averages_away_a_failed_or_unresolved_required_step():
    from chemlab.evidence.chemical_service import summarize_route

    binding = {"steps": [{"input_key": "a"}, {"input_key": "b"}, {"input_key": "a"}]}
    results = {"a": {"evidence_outcome": "support"}, "b": {"evidence_outcome": "contradiction"}}
    summary = summarize_route(binding, results)
    assert summary["evidence_outcome"] == "contradiction"
    assert summary["step_findings"] == {"support": 2, "contradiction": 1}
    results["b"]["evidence_outcome"] = "unresolved"
    assert summarize_route(binding, results)["evidence_outcome"] == "unresolved"
    results["b"]["evidence_outcome"] = "error"
    assert summarize_route(binding, results)["evidence_outcome"] == "error"
    results["b"]["evidence_outcome"] = "support"
    assert summarize_route(binding, results)["evidence_outcome"] == "support"
    assert summarize_route(binding, results)["chemical_feasibility"] == "unresolved"
    with pytest.raises(IntegrityError, match="every selected step"):
        summarize_route(binding, {"a": results["a"]})
