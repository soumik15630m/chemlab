import pytest

from chemlab.adapters.models import ModelService
from chemlab.evidence.checks import forward_check, precedent_lookup
from chemlab.records import Candidate, Corpus, PrecedentSource


@pytest.mark.parametrize(
    "outputs,status",
    [
        ([{"product": "CCOC(C)=O"}], "pass"),
        ([{"product": "CC"}], "fail"),
        ([], "fail"),
        ([{"product": "invalid"}], "error"),
    ],
)
def test_forward_decision_table(lab, outputs, status):
    store, _, register, backward, _ = lab
    _, prediction = backward.backward("CCOC(C)=O", 10)
    candidate = prediction.candidates[0]
    assert isinstance(candidate, Candidate)
    forward_ref = register({"CC(=O)O.CCO": outputs}, "forward")
    assert forward_check(ModelService(store, forward_ref), candidate, 5).status == status


def test_no_precedent_is_successful_retrieval_not_failed_reaction(lab):
    store, _, _, backward, _ = lab
    _, prediction = backward.backward("CCOC(C)=O", 10)
    corpus = Corpus(
        name="Development",
        version="1",
        partition="development",
        source="test",
        license="test",
        multiplicity="occurrences",
        records=(),
    )
    result = precedent_lookup(store, store.put("corpus", corpus), prediction.candidates[0])
    assert result["status"] == "pass" and result["match_type"] == "none"


def test_exact_lookup_returns_all_sources_and_preserves_multiplicity(lab):
    store, _, _, backward, _ = lab
    _, prediction = backward.backward("CCOC(C)=O", 10)
    corpus = Corpus(
        name="Development",
        version="1",
        partition="development",
        source="test",
        license="test",
        multiplicity="occurrences",
        records=(
            PrecedentSource(source_id="a", product="CCOC(C)=O", precursors=("CCO", "CC(=O)O")),
            PrecedentSource(source_id="b", product="CCOC(C)=O", precursors=("CC(=O)O", "OCC")),
            PrecedentSource(
                source_id="c", product="CCOC(C)=O", precursors=("CCO", "CCO", "CC(=O)O")
            ),
        ),
    )
    result = precedent_lookup(store, store.put("corpus", corpus), prediction.candidates[0])
    assert result["exact_source_ids"] == ["a", "b"]
