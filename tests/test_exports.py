import copy
import hashlib
import io
import json
import zipfile
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from rdkit import Chem
from rdkit.Chem import rdChemReactions

from chemlab.api import create_app
from chemlab.application import Application
from chemlab.chemistry import require_molecule
from chemlab.records import Occurrence, Route, Step
from chemlab.reporting.formats import chemistry_zip, molecule_mol, step_files
from chemlab.reporting.pdf import molecule_pdf, report_pdf
from chemlab.store import IntegrityError


@pytest.fixture
def published(lab):
    store, config, *_ = lab
    application = Application(store)
    run_id = application.prepare("CCOC(C)=O", config)
    application.execute(run_id)
    row = application.run(run_id)
    assert row["state"] == "complete", row["error"]
    return row


@pytest.mark.parametrize(
    "smiles",
    [
        "C[C@H](O)F",
        "C[C@@H](O)F",
        "F/C=C/F",
        "F/C=C\\F",
        "[13CH3][C@H](O)[NH3+].[Cl-]",
        "[2H]O[2H]",
        "[Na+].CC(=O)[O-]",
    ],
)
def test_mol_roundtrip_preserves_declared_identity(smiles):
    data = molecule_mol(smiles)
    assert b"V3000" in data
    restored = Chem.MolFromMolBlock(data.decode("ascii"), sanitize=True, removeHs=False)
    assert (
        Chem.MolToSmiles(restored, isomericSmiles=True) == require_molecule(smiles).canonical_smiles
    )


def test_reaction_export_keeps_forward_direction_multiplicity_and_fragments():
    route = Route(
        root_id="p",
        molecules=tuple(
            Occurrence(id=mid, molecule=require_molecule(smiles))
            for mid, smiles in [("p", "CO"), ("a", "[Na+].CO"), ("b", "Cl"), ("c", "Cl")]
        ),
        steps=(
            Step(
                id="s",
                product_id="p",
                precursor_ids=("a", "b", "c"),
                prediction_ref="format-fixture",
                candidate_index=0,
            ),
        ),
        search_cost=0,
        source="Serialization fixture only; no chemical feasibility claim",
    )
    rxn, smiles = step_files(route, route.steps[0])
    for restored in (
        rdChemReactions.ReactionFromRxnBlock(rxn.decode("ascii"), sanitize=True, removeHs=False),
        rdChemReactions.ReactionFromSmarts(smiles, useSmiles=True),
    ):
        assert restored.GetNumReactantTemplates() == 3
        assert restored.GetNumProductTemplates() == 1
        reactants = Counter(
            Chem.MolToSmiles(m, isomericSmiles=True) for m in restored.GetReactants()
        )
        assert reactants == Counter({"CO.[Na+]": 1, "Cl": 2})
        assert Chem.MolToSmiles(restored.GetProductTemplate(0)) == "CO"


def test_chemistry_archive_is_complete_bound_and_deterministic(published):
    bundle = published["result"]
    route_ref = bundle["groups"]["verified_consistent"][0]["route_ref"]
    data = chemistry_zip(bundle, route_ref)
    assert chemistry_zip(bundle, route_ref) == data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["reaction_direction"] == "precursors_to_product"
        assert manifest["route_ref"] == route_ref
        assert len(manifest["molecules"]) == 3
        assert len(manifest["steps"]) == 1
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        molecules = list(Chem.ForwardSDMolSupplier(io.BytesIO(archive.read("molecules.sdf"))))
        expected = bundle["objects"][route_ref]["payload"]["molecules"]
        assert [m.GetProp("occurrence_id") for m in molecules] == [m["id"] for m in expected]
        assert [Chem.MolToSmiles(m) for m in molecules] == [
            m["molecule"]["canonical_smiles"] for m in expected
        ]
        reaction = rdChemReactions.ReactionFromRxnBlock(
            archive.read("reactions/step-0001.rxn").decode("ascii")
        )
        assert reaction.GetNumReactantTemplates() == 2
        assert reaction.GetNumProductTemplates() == 1
        assert b"<svg" in archive.read("reactions/step-0001.svg")


def test_unverified_routes_cannot_receive_editable_chemistry_exports(published):
    bundle = copy.deepcopy(published["result"])
    item = bundle["groups"]["verified_consistent"][0]
    bundle["objects"][item["report_ref"]]["payload"]["structural_status"] = "rejected"
    with pytest.raises(ValueError, match="structurally verified"):
        chemistry_zip(bundle, item["route_ref"])


def test_export_cannot_attach_a_report_to_a_different_route(published):
    bundle = copy.deepcopy(published["result"])
    item = bundle["groups"]["verified_consistent"][0]
    bundle["objects"][item["report_ref"]]["payload"]["route_hash"] = "0" * 64
    with pytest.raises(IntegrityError, match="another route"):
        chemistry_zip(bundle, item["route_ref"])


def test_pdf_keeps_evidence_scope_and_fixture_warning(published):
    bundle = published["result"]
    data = report_pdf(bundle)
    assert data == report_pdf(bundle)
    pdf = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) >= 2
    for expected in (
        "Synthesis route report",
        published["id"],
        "Structural: verified",
        "Forward: consistent",
        "verification-v1.2",
        "Computational fixture",
        "do not prove experimental feasibility",
        "Reaction conditions",
    ):
        assert expected in text
    item = bundle["groups"]["verified_consistent"][0]
    assert item["route_ref"] in text.replace("\n", "")


def test_pdf_records_conflict_and_keeps_rejected_routes_as_diagnostics(published):
    bundle = copy.deepcopy(published["result"])
    item = bundle["groups"]["verified_consistent"][0]
    report = bundle["objects"][item["report_ref"]]["payload"]
    report["forward_status"] = "conflict"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(report_pdf(bundle))).pages)
    assert "Forward: conflict" in text
    report["structural_status"] = "rejected"
    bundle["groups"]["verified_consistent"] = []
    bundle["groups"]["rejected"] = [item]
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(report_pdf(bundle))).pages)
    assert "Rejected diagnostics: 1" in text
    assert "No structurally verified routes" in text
    assert "Transformation s0" not in text


def test_standalone_molecule_pdf_does_not_claim_reaction_verification():
    data = molecule_pdf("[13CH3][C@H](O)F")
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert "Molecular structure" in text
    assert "does not claim a reaction" in text
    assert "Forward:" not in text


def test_download_endpoints_bind_run_route_and_status(lab, published):
    store, config, *_ = lab
    run_id = published["id"]
    route_ref = published["result"]["groups"]["verified_consistent"][0]["route_ref"]
    queued = Application(store).prepare("CCOC(C)=O", config)
    with TestClient(create_app(store.root)) as client:
        assert client.get(f"/api/runs/{run_id}/report.pdf").content.startswith(b"%PDF-")
        response = client.get(f"/api/runs/{run_id}/routes/{route_ref}/chemistry.zip")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert client.get(f"/api/runs/{run_id}/routes/missing/chemistry.zip").status_code == 404
        assert client.get("/api/runs/missing/report.pdf").status_code == 404
        assert client.get(f"/api/runs/{queued}/report.pdf").status_code == 409
        assert client.get("/api/molecule.pdf", params={"smiles": "CCO"}).content.startswith(
            b"%PDF-"
        )
        assert client.get("/api/molecule.mol", params={"smiles": "CCO"}).status_code == 200
        assert client.get("/api/molecule.mol", params={"smiles": "invalid"}).status_code == 400
