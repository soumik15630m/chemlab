import pytest

from chemlab.adapters.models import ModelService
from chemlab.chemistry import require_molecule
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


def test_precedent_cannot_transfer_from_a_carbonyl_analog_to_the_requested_product(lab):
    store, *_ = lab
    target = "N#C/C(C(N)=O)=C1/NCc2ccccc21"
    carbonyl_analog = "N#C/C(C(N)=O)=C1/NC(=O)c2ccccc21"
    precursor = "CCOC(=O)/C(C#N)=C1\\NCc2ccccc21"
    candidate = Candidate(
        index=0,
        product=require_molecule(target),
        precursors=(require_molecule(precursor), require_molecule("N")),
        score=1,
        cost=0,
    )
    corpus = Corpus(
        name="Carbonyl-analog retrieval counterexample",
        version="1",
        partition="development",
        source="Constructed identity fixture; no experimental reaction claim",
        license="test",
        multiplicity="occurrences",
        records=(
            PrecedentSource(
                source_id="analog-only",
                product=carbonyl_analog,
                precursors=(precursor, "N"),
            ),
        ),
    )
    ref = store.put("corpus", corpus)
    assert precedent_lookup(store, ref, candidate)["exact_source_ids"] == []
    analog_candidate = candidate.model_copy(update={"product": require_molecule(carbonyl_analog)})
    assert precedent_lookup(store, ref, analog_candidate)["exact_source_ids"] == ["analog-only"]
