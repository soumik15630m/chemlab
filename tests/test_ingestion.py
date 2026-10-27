import hashlib

import pytest

from chemlab.evidence.ingestion import public_training_csv


def metadata(raw):
    return {
        "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "html_url": "https://github.com/coleygroup/openretro",
    }


def test_original_records_and_quarantine_are_preserved():
    raw = (
        b"id,class,rxn_smiles\nUS1,UNK,[CH3:1][OH:2].[OH2:3]>>[CH2:1]=[O:2]\nUS2,UNK,invalid>>CC\n"
    )
    corpus, audit = public_training_csv(raw, metadata(raw))
    assert corpus.partition == "training" and corpus.multiplicity == "occurrences"
    assert len(corpus.records) == 1
    assert corpus.records[0].source_id == "US1:train-row-1"
    assert corpus.records[0].precursors == ("[CH3:1][OH:2]", "[OH2:3]")
    assert audit["input_records"] == 2 and audit["accepted_records"] == 1
    assert audit["quarantined"][0]["original"]["rxn_smiles"] == "invalid>>CC"


def test_source_blob_mismatch_is_rejected():
    raw = b"id,rxn_smiles\nUS1,CC>>C\n"
    with pytest.raises(ValueError, match="Git blob"):
        public_training_csv(raw + b"\n", metadata(raw))


def test_registered_corpus_binds_source_bytes_and_detects_corruption(tmp_path):
    from chemlab.chemistry import require_molecule
    from chemlab.evidence.checks import precedent_lookup
    from chemlab.evidence.ingestion import register_public_training
    from chemlab.records import Candidate
    from chemlab.reporting.bundles import references
    from chemlab.store import Store

    raw = b"id,rxn_smiles\nUS1,[CH3:1][OH:2]>>[CH2:1]=[O:2]\n"
    store = Store(tmp_path / "store")
    result = register_public_training(store, raw, metadata(raw))
    candidate = Candidate(
        index=0,
        product=require_molecule("C=O"),
        precursors=(require_molecule("CO"),),
        score=1,
        cost=0,
    )
    lookup = precedent_lookup(store, result["corpus_ref"], candidate)
    assert lookup["exact_source_ids"] == ["US1:train-row-1"]
    assert references("corpus", store.get(result["corpus_ref"])) == {
        result["source_ref"],
        result["audit_ref"],
    }
    (store.objects / f"{result['source_ref']}.json").write_bytes(b"{}")
    assert precedent_lookup(store, result["corpus_ref"], candidate)["status"] == "error"
