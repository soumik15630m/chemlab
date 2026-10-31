import hashlib

import pytest

from chemlab.evaluation.chemical_reference import prepare_reference, score_reference
from chemlab.store import IntegrityError


def prepare(raw):
    protocol = {
        "bytes": len(raw),
        "git_blob": hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw,
        ).hexdigest(),
        "expected_rows": 4,
        "expected_label_counts": {"0": 2, "1": 2},
    }
    return prepare_reference(raw, protocol), protocol


RAW = (
    b"reaction_smiles,expert_score,chemcensor_score,chemcensor_score_bin\n"
    b"CCO>>CC=O,1,DO_NOT_USE,DO_NOT_USE\n"
    b"OCC>>O=CC,0,DO_NOT_USE,DO_NOT_USE\n"
    b"C[C@H](O)F>>C[C@H](O)F,1,DO_NOT_USE,DO_NOT_USE\n"
    b"C[C@@H](O)F>>C[C@@H](O)F,0,DO_NOT_USE,DO_NOT_USE\n"
)


def test_checker_inputs_exclude_labels_and_generated_scores_and_group_stereo():
    prepared, _ = prepare(RAW)
    assert prepared["input_rows"] == 4
    assert len(prepared["inputs"]) == 3
    for query in prepared["inputs"].values():
        assert set(query) == {"key", "product", "precursors", "partition", "group"}
    stereo = [query for query in prepared["inputs"].values() if "@" in query["product"]]
    assert stereo[0]["group"] == stereo[1]["group"]
    assert stereo[0]["partition"] == stereo[1]["partition"]
    assert stereo[0]["key"] != stereo[1]["key"]


def test_duplicate_conflicts_and_denominators_are_not_silent_truth():
    prepared, _ = prepare(RAW)
    results = {
        key: {
            "input_key": key,
            "policy_hash": "test-policy",
            "evidence_outcome": "unresolved",
            "checks": {
                "exact_precedent": {"status": "not_checked"},
                "context_precedent": {"status": "not_checked"},
            },
        }
        for key in prepared["inputs"]
    }
    report = score_reference(prepared, results, "test-policy")
    assert report["all_reference_rows"] == 4
    assert sum(v.get("reference_conflicts", 0) for v in report["metrics"].values()) == 1
    assert sum(v.get("unique_inputs", 0) for v in report["metrics"].values()) == 3
    assert sum(v.get("expert_0/unresolved", 0) for v in report["metrics"].values()) == 1
    assert sum(v.get("expert_1/unresolved", 0) for v in report["metrics"].values()) == 1
    with pytest.raises(ValueError, match="Every"):
        score_reference(prepared, {}, "test-policy")


def test_reference_source_and_result_bindings_are_checked():
    prepared, protocol = prepare(RAW)
    with pytest.raises(IntegrityError, match="frozen source"):
        prepare_reference(RAW.replace(b"DO_NOT_USE", b"DO_NOT_SEE"), protocol)
    results = {
        key: {"input_key": key, "policy_hash": "wrong-policy", "evidence_outcome": "support"}
        for key in prepared["inputs"]
    }
    with pytest.raises(IntegrityError, match="policy"):
        score_reference(prepared, results, "test-policy")


def test_reference_hash_aliases_cannot_merge_unrelated_expert_labels(monkeypatch):
    monkeypatch.setattr("chemlab.evaluation.chemical_reference.digest", lambda value: "0" * 64)
    with pytest.raises(IntegrityError, match="Different full reference identities"):
        prepare(RAW)
