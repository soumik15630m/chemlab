import math

import pytest
from pydantic import ValidationError
from syntheseus import Molecule

from chemlab.adapters.models import ModelService, SearchModel, score_cost
from chemlab.records import Candidate, CandidateError, ModelManifest, Prediction


def test_raw_predictions_survive_dedup(lab):
    store, _, _, service, _ = lab
    model = SearchModel(service, 10)
    reactions = model([Molecule("CCOC(C)=O")])[0]
    assert len(reactions) == 1
    assert reactions[0].metadata["candidate_index"] == 0
    record = Prediction.model_validate(store.prediction(reactions[0].metadata["prediction_ref"]))
    assert len(record.raw_output) == 2
    assert len(record.candidates) == 2
    assert [m.canonical_smiles for m in record.candidates[1].precursors] == ["CC(=O)O", "CCO"]
    assert len(reactions[0].metadata["contributors"]) == 2


def test_cache_preserves_logical_attempts(lab):
    _, _, _, service, _ = lab
    model = SearchModel(service, 10)
    assert model([Molecule("CCOC(C)=O")]) == model([Molecule("CCOC(C)=O")])
    assert model.logical_expansions == 2
    assert service.actual_inferences == 1
    second_service = ModelService(service.store, service.manifest_ref)
    second_service.backward("CCOC(C)=O", 10)
    assert second_service.actual_inferences == 0
    assert second_service.cache_hits == 1


def test_direct_adapter_parity(lab):
    _, _, _, service, _ = lab
    _, prediction = service.backward("CCOC(C)=O", 10)
    reactions = SearchModel(service, 10)([Molecule("CCOC(C)=O")])[0]
    best = next(c for c in prediction.candidates if isinstance(c, Candidate) and c.index == 0)
    assert {m.smiles for m in reactions[0].reactants} == {"CCO", "CC(=O)O"}
    assert reactions[0].metadata["chemlab_cost"] == best.cost == -math.log(0.8)


def test_lower_cost_duplicate_wins(lab):
    store, _, register, _, _ = lab
    ref = register(
        {"CC": [{"precursors": ["C"], "score": 0.2}, {"precursors": ["C"], "score": 0.8}]}
    )
    manifest = ModelManifest.model_validate(store.get(ref, "model_manifest"))
    manifest = manifest.model_copy(
        update={"score_semantics": "negative_log_cost", "score_direction": "lower"}
    )
    service = ModelService(store, store.put("model_manifest", manifest))
    reactions = SearchModel(service, 10)([Molecule("CC")])[0]
    assert reactions[0].metadata["chemlab_cost"] == 0.2
    assert reactions[0].metadata["candidate_index"] == 0


def test_error_variants_and_nonfinite_scores(lab):
    store, _, _, _, _ = lab
    with pytest.raises(ValueError):
        store.put("untrusted", {"score": float("nan")})


def test_schema_rejects_nonfinite_and_bad_direction(lab):
    _, _, _, service, _ = lab
    with pytest.raises(ValueError):
        score_cost(float("nan"), service.manifest)
    with pytest.raises(ValueError):
        score_cost(0, service.manifest)
    data = service.manifest.model_dump()
    data["score_direction"] = "lower"
    with pytest.raises(ValidationError):
        ModelManifest.model_validate(data)


def test_invalid_molecule_kept_as_candidate_error(lab):
    store, _, register, _, _ = lab
    ref = register({"CC": [{"precursors": ["not-a-molecule"], "score": 0.8}]})
    _, prediction = ModelService(store, ref).backward("CC", 10)
    assert isinstance(prediction.candidates[0], CandidateError)
    assert "score" not in prediction.candidates[0].model_dump()


def test_inference_error_has_no_fake_candidates(lab, monkeypatch):
    _, _, _, service, _ = lab

    def fail(*args):
        raise TimeoutError("test timeout")

    monkeypatch.setattr(service, "_raw", fail)
    _, result = service.backward("CC", 10)
    assert result.status == "error" and result.candidates == ()
    assert service.store.cache_get({"irrelevant": "key"}) is None


def test_nonfinite_backend_output_remains_a_replayable_error(lab, monkeypatch):
    store, _, _, service, _ = lab
    monkeypatch.setattr(service, "_raw", lambda *_: [{"precursors": ["C"], "score": float("nan")}])
    ref, prediction = service.backward("CC", 10)
    assert prediction.status == "error" and prediction.candidates == ()
    assert store.prediction(ref)["raw_output"]["encoding"] == "python-repr-of-noncanonical-output"
