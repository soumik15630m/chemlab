from copy import deepcopy

import pytest

from chemlab.adapters.models import ModelService
from chemlab.chemistry import require_molecule
from chemlab.records import Check, ModelManifest, Occurrence, Route, Step
from chemlab.verification import verify
from chemlab.verification.verifier import disposition


def test_valid_route_is_verified_and_consistent(lab, ester_route):
    store, config, _, _, forward = lab
    report = verify(store, ester_route.model_dump(mode="json"), "CCOC(C)=O", config, forward)
    assert report.structural_status == "verified"
    assert report.forward_status == "consistent"
    assert report.mapping_coverage == {"checked": 0, "missing": 1, "failed": 0}
    assert next(c for c in report.checks if c.name == "forward:s0").settings["matching_rank"] == 1


@pytest.mark.parametrize(
    "corruption",
    [
        "drop_precursor",
        "replace_precursor",
        "wrong_root",
        "duplicate_occurrence",
        "unreachable",
        "wrong_canonical",
        "wrong_candidate",
        "shared_node",
    ],
)
def test_export_corruptions_are_rejected(lab, ester_route, corruption):
    store, config, _, _, forward = lab
    data = deepcopy(ester_route.model_dump(mode="json"))
    if corruption == "drop_precursor":
        data["molecules"].pop()
        data["steps"][0]["precursor_ids"] = ["m1"]
    elif corruption == "replace_precursor":
        data["molecules"][1]["molecule"] = require_molecule("CC(=O)O").model_dump(mode="json")
    elif corruption == "wrong_root":
        data["root_id"] = "m1"
    elif corruption == "duplicate_occurrence":
        data["molecules"].append(data["molecules"][1])
    elif corruption == "unreachable":
        data["molecules"].append({"id": "unused", "molecule": require_molecule("C").model_dump()})
    elif corruption == "wrong_canonical":
        data["molecules"][0]["molecule"]["canonical_smiles"] = "CC"
    elif corruption == "wrong_candidate":
        data["steps"][0]["candidate_index"] = 99
    else:
        data["steps"][0]["precursor_ids"] = ["m1", "m1", "m2"]
    assert verify(store, data, "CCOC(C)=O", config, forward).structural_status == "rejected"


def test_wrong_target_stereo_is_rejected(lab, ester_route):
    store, config, *_ = lab
    assert (
        verify(store, ester_route.model_dump(mode="json"), "CC", config).structural_status
        == "rejected"
    )


def test_unregistered_hash_is_not_inference_provenance(lab, ester_route):
    store, config, *_ = lab
    data = ester_route.model_dump(mode="json")
    prediction = store.get(data["steps"][0]["prediction_ref"], "prediction")
    prediction["settings"]["fabricated"] = True
    fake = store.put("prediction", prediction)
    data["steps"][0]["prediction_ref"] = fake
    report = verify(store, data, "CCOC(C)=O", config)
    assert report.structural_status == "unresolved"
    assert any("adapter boundary" in c.reason for c in report.checks)


def test_mapping_required_is_unresolved_when_missing(lab, ester_route):
    store, config, *_ = lab
    strict = config.model_copy(update={"mapping_profile": "mapping-required"})
    assert (
        verify(store, ester_route.model_dump(mode="json"), "CCOC(C)=O", strict).structural_status
        == "unresolved"
    )


def test_auxiliary_mapping_failure_does_not_reject(lab, ester_route):
    store, config, register, _, _ = lab
    ref = register(
        {
            "CCOC(C)=O": [
                {
                    "precursors": ["CCO", "CC(=O)O"],
                    "score": 0.8,
                    "mapped_reaction": "[CH3:1][OH:1]>>[CH2:1]=[O:2]",
                }
            ]
        }
    )
    pred_ref, _ = ModelService(store, ref).backward("CCOC(C)=O", 10)
    data = ester_route.model_dump(mode="json")
    data["steps"][0]["prediction_ref"] = pred_ref
    config = config.model_copy(update={"backward_manifest": ref})
    result = verify(store, data, "CCOC(C)=O", config)
    assert result.structural_status == "verified"
    assert result.mapping_coverage["failed"] == 1
    strict = config.model_copy(update={"mapping_profile": "mapping-required"})
    assert verify(store, data, "CCOC(C)=O", strict).structural_status == "rejected"


def test_template_replay_is_mandatory(lab, ester_route):
    store, config, register, _, _ = lab
    template = "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])O.[O:3][C:4]"
    ref = register(
        {"CCOC(C)=O": [{"precursors": ["CCO", "CC(=O)O"], "score": 0.8, "template_id": "ester"}]},
        "template_based",
        templates={"ester": template},
        template_order=("ester",),
    )
    pred_ref, _ = ModelService(store, ref).backward("CCOC(C)=O", 10)
    data = ester_route.model_dump(mode="json")
    data["steps"][0]["prediction_ref"] = pred_ref
    cfg = config.model_copy(update={"backward_manifest": ref})
    result = verify(store, data, "CCOC(C)=O", cfg)
    assert result.structural_status == "verified"
    assert next(c for c in result.checks if c.name == "template:s0").status == "pass"
    manifest = ModelManifest.model_validate(store.get(ref, "model_manifest"))
    broken = manifest.model_copy(
        update={"templates": {"ester": "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])[O:3].[C:4]"}}
    )
    broken_ref = store.put("model_manifest", broken)
    broken_pred, _ = ModelService(store, broken_ref).backward("CCOC(C)=O", 10)
    data["steps"][0]["prediction_ref"] = broken_pred
    assert (
        verify(
            store, data, "CCOC(C)=O", cfg.model_copy(update={"backward_manifest": broken_ref})
        ).structural_status
        == "rejected"
    )


def test_molecular_cycle_with_fresh_occurrences(lab):
    store, config, *_ = lab
    route = Route(
        root_id="m0",
        molecules=tuple(
            Occurrence(id=f"m{i}", molecule=require_molecule(s))
            for i, s in enumerate(["CC", "CCC", "CC"])
        ),
        steps=(
            Step(
                id="s0",
                product_id="m0",
                precursor_ids=("m1",),
                prediction_ref="0" * 64,
                candidate_index=0,
            ),
            Step(
                id="s1",
                product_id="m1",
                precursor_ids=("m2",),
                prediction_ref="0" * 64,
                candidate_index=0,
            ),
        ),
        search_cost=0,
        source="test",
    )
    result = verify(store, route.model_dump(mode="json"), "CC", config)
    assert result.structural_status == "rejected"
    assert any("ancestor recurrence" in c.reason for c in result.checks)


def test_fail_dominates_unknown():
    assert (
        disposition(
            [
                Check(name="a", status="unknown", reason="missing"),
                Check(name="b", status="fail", reason="wrong"),
            ]
        )
        == "rejected"
    )
    assert disposition([Check(name="a", status="error", reason="timeout")]) == "unresolved"


def test_nonfinite_export_is_rejected_without_fabricated_success(lab, ester_route):
    store, config, *_ = lab
    data = ester_route.model_dump(mode="json")
    data["search_cost"] = float("nan")
    report = verify(store, data, "CCOC(C)=O", config)
    assert report.structural_status == "rejected"
    assert report.checks[0].name == "schema" and report.checks[0].status == "fail"


def test_mapping_binding_preserves_disconnected_precursor_identity(lab):
    from chemlab.evidence.checks import import_stock

    store, config, register, *_ = lab
    ref = register(
        {
            "CO": [
                {
                    "precursors": ["C.[Na+]", "O"],
                    "score": 0.8,
                    "mapped_reaction": "[CH4:1].[Na+:3].[OH2:2]>>[CH3:1][OH:2]",
                }
            ]
        }
    )
    prediction_ref, _ = ModelService(store, ref).backward("CO", 10)
    stock_ref = import_stock(store, ["C.[Na+]", "O"], "mapping fixture", "test", "test")
    route = Route(
        root_id="m0",
        molecules=tuple(
            Occurrence(id=f"m{i}", molecule=require_molecule(s))
            for i, s in enumerate(["CO", "C.[Na+]", "O"])
        ),
        steps=(
            Step(
                id="s0",
                product_id="m0",
                precursor_ids=("m1", "m2"),
                prediction_ref=prediction_ref,
                candidate_index=0,
            ),
        ),
        search_cost=0.2231435513142097,
        source="computational mapping fixture",
    )
    cfg = config.model_copy(
        update={
            "backward_manifest": ref,
            "stock_ref": stock_ref,
            "mapping_profile": "mapping-required",
        }
    )
    report = verify(store, route.model_dump(mode="json"), "CO", cfg)
    assert report.structural_status == "verified"
    assert report.mapping_coverage["failed"] == 0
