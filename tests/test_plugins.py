import json

import pytest

from chemlab.adapters.models import ModelService
from chemlab.adapters.sdk import content_hash, validate_tokenization
from chemlab.evaluation.datasets import ReactionExample, audit, export_training
from chemlab.records import ModelManifest
from chemlab.registry import Registry, parity


def test_deterministic_template_plugin_uses_same_adapter_contract(lab, tmp_path):
    store, *_ = lab
    vocabulary = {"ester": "[C:1](=[O:2])[O:3][C:4]>>[C:1](=[O:2])O.[O:3][C:4]"}
    path = tmp_path / "templates.json"
    path.write_text(json.dumps(vocabulary), encoding="ascii")
    manifest = ModelManifest(
        name="Deterministic template fixture",
        kind="template_based",
        backend="python",
        checkpoint=str(path),
        checkpoint_hash=content_hash(path),
        training_provenance="synthetic test",
        license="test",
        score_semantics="cost",
        score_direction="lower",
        templates=vocabulary,
        template_order=("ester",),
        architecture_id="template-enumeration-v1",
        model_class="chemlab.adapters.sdk:TemplateLibraryProvider",
    )
    registry = Registry(store)
    ref = registry.register_model("templates-v1", manifest)
    _, result = ModelService(store, ref).backward("CCOC(C)=O", 10)
    assert result.status == "ok"
    assert {m.canonical_smiles for m in result.candidates[0].precursors} == {"CCO", "CC(=O)O"}
    assert parity(store, ref, ["CCOC(C)=O"], 10)["passed"]
    path.write_text("changed", encoding="ascii")
    with pytest.raises(ValueError, match="Checkpoint content changed"):
        registry.register_model("changed", manifest)


def test_registry_alias_cannot_silently_change(lab):
    store, config, *_ = lab
    registry = Registry(store)
    registry.register("model-v1", "model_manifest", config.backward_manifest)
    with pytest.raises(ValueError, match="immutable"):
        registry.register("model-v1", "model_manifest", config.forward_manifest)


def test_training_export_excludes_final_reference_and_audits_overlap(tmp_path):
    examples = [
        ReactionExample(
            source_id="train", product="CCO", precursors=("CC", "O"), partition="training"
        ),
        ReactionExample(
            source_id="final", product="OCC", precursors=("O", "CC"), partition="final_reference"
        ),
    ]
    report = audit(examples)
    assert report["overlap"]["training:final_reference"] == {
        "reaction_overlap": 1,
        "target_overlap": 1,
    }
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="overlap final-reference"):
        export_training(examples, output)
    examples[1] = examples[1].model_copy(update={"product": "CCC", "precursors": ("CC", "C")})
    export_training(examples, output)
    training = (output / "training.jsonl").read_text()
    assert '"train"' in training and '"final"' not in training
    assert not (output / "final_reference.jsonl").exists()


def test_tokenizer_cannot_silently_lose_input_information():
    import re
    from types import SimpleNamespace

    tokenizer = SimpleNamespace(
        regex=re.compile(r"C|O|N|#|\[[^\]]+\]"), vocab_dict={"C": 0, "O": 1, "N": 2, "#": 3}
    )
    validate_tokenization(tokenizer, "CCO", 512)
    with pytest.raises(ValueError, match="vocabulary"):
        validate_tokenization(tokenizer, "[13CH3]O", 512)
    with pytest.raises(ValueError, match="discards"):
        validate_tokenization(tokenizer, "C(C)O", 512)
    with pytest.raises(ValueError, match="sequence limit"):
        validate_tokenization(tokenizer, "CCO", 2)
