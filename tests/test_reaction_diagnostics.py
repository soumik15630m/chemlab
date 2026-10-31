import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chemlab.api import create_app
from chemlab.application import Application
from chemlab.chemistry import require_molecule
from chemlab.evaluation.reaction_challenges import evaluate_challenges
from chemlab.evidence.reaction_diagnostics import (
    atom_inventory,
    diagnose_route,
    mapped_edits,
    representation_diagnostic,
)
from chemlab.records import canonical_bytes
from chemlab.store import IntegrityError

FIXTURES = Path(__file__).parent / "fixtures" / "reaction-challenges"


def test_atom_inventory_keeps_occurrences_isotopes_and_omitted_reagent_limits():
    result = atom_inventory("[13CH3]CO", ("C", "C", "[Na+].[Cl-]"))
    assert result["status"] == "observed"
    assert result["counts"] == [
        {"element": "C", "isotope": 0, "listed_precursors": 2, "product": 1},
        {"element": "C", "isotope": 13, "listed_precursors": 0, "product": 1},
        {"element": "Cl", "isotope": 0, "listed_precursors": 1, "product": 0},
        {"element": "Na", "isotope": 0, "listed_precursors": 1, "product": 0},
        {"element": "O", "isotope": 0, "listed_precursors": 0, "product": 1},
    ]
    assert result["elements_without_listed_source"] == ["O"]
    assert result["isotope_labels_without_listed_source"] == [["C", 13]]
    assert "not stoichiometric" in result["count_basis"]
    assert atom_inventory("CC", ("C",))["status"] == "observed"
    assert atom_inventory("CC", ("C",))["elements_without_listed_source"] == []


@pytest.mark.parametrize("product,precursors", [("invalid", ("C",)), ("C", ()), ("C", ("*",))])
def test_inventory_errors_cannot_become_completed_observations(product, precursors):
    assert atom_inventory(product, precursors)["status"] == "error"


def test_mapped_edits_observe_substitution_and_lost_atoms_not_mechanistic_proof():
    result = mapped_edits("CO", ("CBr", "[OH-]"), "[CH3:1][Br:2].[OH-:3]>>[CH3:1][OH:3]")
    assert result["status"] == "observed"
    assert result["appeared_in_product"] == [{"maps": [1, 3], "order": "SINGLE"}]
    assert result["absent_from_product"] == [{"maps": [1, 2], "order": "SINGLE"}]
    assert result["reactant_maps_absent_from_product"] == [2]
    assert result["formal_charge_changes"] == [{"map": 3, "before": -1, "after": 0}]
    result = mapped_edits("CC=O", ("CCO",), "[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]")
    assert result["order_changed"] == [{"maps": [2, 3], "before": "SINGLE", "after": "DOUBLE"}]
    assert result["appeared_in_product"] == []


@pytest.mark.parametrize(
    "product,precursors,mapping,reason",
    [
        ("CO", ("CBr", "[OH-]"), None, "mapping_missing"),
        ("CO", ("CBr", "[OH-]"), "[CH3:1][Br:2].[OH-:3]>>[CH3:1][OH:1]", "duplicate_map_number"),
        (
            "CO",
            ("CBr", "[OH-]"),
            "[CH3:1][Br:2].[OH-:3]>>[CH3:1][OH:2]",
            "mapped_element_or_isotope_mismatch",
        ),
        (
            "CN",
            ("CBr", "[OH-]"),
            "[CH3:1][Br:2].[OH-:3]>>[CH3:1][OH:3]",
            "mapping_reaction_identity_mismatch",
        ),
        (
            "CO",
            ("CBr", "[OH-]", "C"),
            "[CH3:1][Br:2].[OH-:3].C>>[CH3:1][OH:3]",
            "unmapped_atoms_prevent_complete_edit_observation",
        ),
    ],
)
def test_invalid_or_inapplicable_mapping_never_supplies_edits(product, precursors, mapping, reason):
    result = mapped_edits(product, precursors, mapping)
    assert result["status"] == "unknown"
    assert result["reason"] == reason
    assert "appeared_in_product" not in result


def test_tautomer_diagnostic_preserves_rank_identity_and_complete_enumeration():
    expected = "CC1=NNC(=O)C1"
    hydroxy = "Cc1cc(O)[nH]n1"
    assert require_molecule(expected).canonical_smiles != require_molecule(hydroxy).canonical_smiles
    result = representation_diagnostic(expected, ("C", hydroxy, expected))
    assert result["comparisons"] == [
        {"rank": 1, "relation": "different_enumerated_tautomer"},
        {"rank": 2, "relation": "shared_enumerated_tautomer"},
        {"rank": 3, "relation": "exact_identity"},
    ]
    limited = representation_diagnostic("CC=O", ("C=CO",), max_tautomers=1)
    assert limited["comparisons"][0]["relation"] == "unknown"
    assert limited["comparisons"][0]["reason"] == "tautomer_enumeration_incomplete"
    assert representation_diagnostic("C", ("invalid",))["status"] == "error"
    assert representation_diagnostic("C", ())["status"] == "unknown"


def test_tautomer_diagnostic_does_not_collapse_stereo_isotopes_charge_or_fragments():
    for left, right in [("F/C=C/F", "F/C=C\\F"), ("[13CH3]C=O", "CC=O")]:
        result = representation_diagnostic(left, (right,))
        assert result["comparisons"][0]["relation"] == "unknown"
    for left, right in [("C[NH3+]", "CN"), ("CC(=O)[O-].[Na+]", "CC(=O)O")]:
        assert (
            representation_diagnostic(left, (right,))["comparisons"][0]["relation"]
            == "different_enumerated_tautomer"
        )


@pytest.fixture(scope="module")
def challenge_inputs():
    return (
        json.loads((FIXTURES / "snapshot.json").read_text(encoding="ascii")),
        json.loads((FIXTURES / "labels.json").read_text(encoding="ascii")),
    )


def test_development_challenges_expose_forward_counterexamples_without_relabelling(
    challenge_inputs,
):
    snapshot, labels = challenge_inputs
    assert hashlib.sha256((FIXTURES / "snapshot.json").read_bytes()).hexdigest() == (
        "771cd13845e7f8324144b14d615875ae102ebcf4e9a14fffd9c27b75b0fde602"
    )
    before = canonical_bytes(snapshot)
    report = evaluate_challenges(snapshot, labels)
    assert report["route_counts"] == {"correct": 3, "incorrect": 9, "unlabelled": 2}
    assert report["step_occurrences"] == 39
    assert report["forward_status_by_user_label"] == {
        "correct/conflict": 1,
        "correct/consistent": 2,
        "incorrect/conflict": 7,
        "incorrect/consistent": 2,
        "unlabelled/conflict": 1,
        "unlabelled/consistent": 1,
    }
    assert canonical_bytes(snapshot) == before
    assert canonical_bytes(evaluate_challenges(snapshot, labels)) == canonical_bytes(report)
    for row in report["routes"]:
        assert row["step_labels"] == "not_supplied"
        assert row["observations"]["chemical_assessment"] == "unresolved"
        assert all(
            s["atom_inventory"]["status"] == "observed" for s in row["observations"]["steps"]
        )
    pyrazolone = next(
        row
        for row in report["routes"]
        if row["run_id"].startswith("4707") and row["pdf_route_number"] == 4
    )
    step = pyrazolone["observations"]["steps"][0]
    assert step["recorded_forward_status"] == "fail"
    assert [
        r["rank"]
        for r in step["forward_representation"]["comparisons"]
        if r["relation"] == "shared_enumerated_tautomer"
    ] == [2, 5]
    assert all(
        row["observations"]["recorded_structural_status"] == "verified" for row in report["routes"]
    )


def test_challenge_labels_are_not_consumed_by_diagnostics(challenge_inputs):
    snapshot, labels = challenge_inputs
    alternate = copy.deepcopy(labels)
    alternate["reports"]["470792e991c24516ac93beda4c2fd67a"]["1"] = "incorrect"
    one = evaluate_challenges(snapshot, labels)
    two = evaluate_challenges(snapshot, alternate)
    assert [r["observations"] for r in one["routes"]] == [r["observations"] for r in two["routes"]]


def test_challenge_rejects_tampering_missing_evidence_and_final_partition(challenge_inputs):
    snapshot, labels = challenge_inputs
    changed = copy.deepcopy(snapshot)
    ref = changed["reports"][0]["completion"]["groups"]["verified_consistent"][0]["route_ref"]
    changed["objects"][ref]["payload"]["search_cost"] += 1
    with pytest.raises(IntegrityError, match="hash"):
        evaluate_challenges(changed, labels)
    changed = copy.deepcopy(snapshot)
    del changed["objects"][ref]
    with pytest.raises(IntegrityError, match="diagnostic input"):
        evaluate_challenges(changed, labels)
    final = {**labels, "partition": "final_reference"}
    with pytest.raises(ValueError, match="development"):
        evaluate_challenges(snapshot, final)


def test_route_diagnostics_reject_a_route_outside_the_run(challenge_inputs):
    snapshot, _ = challenge_inputs
    bundle = {**snapshot["reports"][0]["completion"], "objects": snapshot["objects"]}
    other = snapshot["reports"][1]["completion"]["groups"]["verified_consistent"][0]["route_ref"]
    with pytest.raises(KeyError):
        diagnose_route(bundle, other)


def test_diagnostics_require_original_prediction_hash_even_when_chemistry_is_unchanged(
    challenge_inputs,
):
    snapshot, _ = challenge_inputs
    bundle = {**snapshot["reports"][0]["completion"], "objects": copy.deepcopy(snapshot["objects"])}
    ref = bundle["groups"]["verified_consistent"][0]["route_ref"]
    prediction = bundle["objects"][ref]["payload"]["steps"][0]["prediction_ref"]
    bundle["objects"][prediction]["payload"]["raw_output"] = []
    with pytest.raises(IntegrityError, match="corrupt"):
        diagnose_route(bundle, ref)


def test_observations_endpoint_is_bound_read_only_and_preserves_positive_route(lab):
    store, config, *_ = lab
    app = Application(store)
    run_id = app.prepare("CCOC(C)=O", config)
    app.execute(run_id)
    row = app.run(run_id)
    bundle = row["result"]
    before = canonical_bytes(bundle)
    ref = bundle["groups"]["verified_consistent"][0]["route_ref"]
    path = f"/api/runs/{run_id}/routes/{ref}/observations.json"
    with TestClient(create_app(store.root)) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        observations = response.json()
        assert observations["chemical_assessment"] == "unresolved"
        assert observations["recorded_structural_status"] == "verified"
        assert observations["recorded_forward_status"] == "consistent"
        assert observations["steps"][0]["mapped_edits"]["reason"] == "mapping_missing"
        assert observations["steps"][0]["forward_representation"]["comparisons"] == [
            {"rank": 1, "relation": "exact_identity"}
        ]
        assert client.get(path).content == response.content
        assert client.get(f"/api/runs/{run_id}/routes/missing/observations.json").status_code == 404
        assert client.get("/api/runs/missing/routes/missing/observations.json").status_code == 404
        queued = app.prepare("CCOC(C)=O", config)
        assert client.get(f"/api/runs/{queued}/routes/{ref}/observations.json").status_code == 409
    assert canonical_bytes(app.run(run_id)["result"]) == before
