import hashlib
import json
import sqlite3

import pytest

from chemlab.evidence.reaction_library import (
    HEADER,
    ReactionLibrary,
    build_library,
    file_digest,
    index_reaction_inputs,
    materialize_snapshot,
    parse_patent_line,
)
from chemlab.records import canonical_bytes, digest
from chemlab.store import IntegrityError

# Software contract fixtures; not chemical feasibility or evaluation records.
OXIDATION = b"[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]\tUS-fixture\t1\t2000\n"


def source(tmp_path, rows):
    path = tmp_path / "source.rsmi"
    path.write_bytes(HEADER.encode() + b"\n" + b"".join(rows))
    return {
        "id": "software-contract-fixture",
        "path": str(path),
        "sha256": file_digest(path),
        "kind": "reported_patent",
        "partition": "training",
        "license": "test-only",
    }


def library(tmp_path, rows):
    spec = source(tmp_path, rows)
    root = tmp_path / "library"
    manifest = build_library([spec], root)
    return root, manifest, ReactionLibrary(root, file_digest(root / "manifest.json"))


def test_lookup_exact_identity_occurrences_and_duplicate_provenance(tmp_path):
    root, manifest, index = library(tmp_path, [OXIDATION, OXIDATION])
    assert manifest["counts"] == {
        "input_rows": 2,
        "accepted_rows": 2,
        "mapping_pass": 2,
        "unique_reactions": 1,
    }
    result = index.lookup("O=CC", ("OCC",), limit=1)
    assert result["status"] == "reported_match"
    assert result["chemical_feasibility"] == "unresolved"
    assert (result["total_matches"], result["returned_matches"]) == (2, 1)
    assert result["matches"][0]["row"] == 1
    assert result["matches"][0]["raw_sha256"] == hashlib.sha256(OXIDATION).hexdigest()
    for product, precursors in [
        ("CCO", ("CCO",)),
        ("CC=O", ("CCO", "CCO")),
        ("[13CH3]C=O", ("CCO",)),
        ("CC=O", ("CCO", "[Na+]")),
    ]:
        assert index.lookup(product, precursors)["status"] == "unknown"
    assert (root / "complete.json").exists()


def test_stereo_charge_fragments_and_isotopes_are_not_merged(tmp_path):
    row = b"C[C@H](O)F.[Na+]>>[13CH3]O\tUS-fixture\t1\t2000\n"
    _, _, index = library(tmp_path, [row])
    assert index.lookup("[13CH3]O", ("C[C@H](O)F", "[Na+]"))["status"] == "reported_match"
    for product, precursors in [
        ("CO", ("C[C@H](O)F", "[Na+]")),
        ("[13CH3]O", ("C[C@@H](O)F", "[Na+]")),
        ("[13CH3]O", ("C[C@H](O)F",)),
        ("[13CH3]O", ("C[C@H](O)F", "[Na]")),
    ]:
        assert index.lookup(product, precursors)["status"] == "unknown"


def test_final_reference_excluded_before_any_claim_is_returned(tmp_path):
    _, _, index = library(tmp_path, [OXIDATION])
    result = index.lookup(
        "CC=O",
        ("CCO",),
        excluded=frozenset(
            {
                digest({"product": "CC=O", "precursors": ["CCO"]}),
            }
        ),
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "final_reference_identity_excluded"
    assert result["matches"] == []


def test_unsupported_and_broken_sources_remain_quarantined(tmp_path):
    _, manifest, index = library(
        tmp_path,
        [
            OXIDATION,
            b"C>>C |f:0.1|\tUS-fixture\t1\t2000\n",
            b"C>>*\tUS-fixture\t1\t2000\n",
            b"invalid-row\n",
        ],
    )
    assert manifest["counts"]["quarantined_rows"] == 3
    assert manifest["counts"]["accepted_rows"] == 1
    assert index.lookup("CC=O", ("CCO",))["status"] == "reported_match"
    spec = source(tmp_path, [OXIDATION])
    spec["sha256"] = "0" * 64
    with pytest.raises(IntegrityError, match="pinned"):
        build_library([spec], tmp_path / "bad-source")
    spec["partition"] = "final_reference"
    with pytest.raises(ValueError, match="training"):
        build_library([spec], tmp_path / "final-source")


def test_incomplete_tampered_or_changed_library_never_supplies_evidence(tmp_path):
    root, _, index = library(tmp_path, [OXIDATION])
    expected = file_digest(root / "manifest.json")
    with pytest.raises(IntegrityError, match="manifest"):
        ReactionLibrary(root, "0" * 64)
    with sqlite3.connect(root / "reactions.sqlite3") as conn:
        conn.execute("UPDATE records SET raw=?", (OXIDATION.replace(b"US-fixture", b"US-tamper"),))
    with pytest.raises(IntegrityError, match="changed"):
        index.lookup("CC=O", ("CCO",))
    with pytest.raises(IntegrityError, match="database"):
        ReactionLibrary(root, expected)
    (root / "complete.json").write_text(json.dumps({"manifest_sha256": "0" * 64}))
    with pytest.raises(IntegrityError, match="published"):
        ReactionLibrary(root, expected)
    with pytest.raises(FileExistsError):
        build_library([], root)


def test_parallel_source_parsing_preserves_claims_and_order(tmp_path):
    spec = source(tmp_path, [OXIDATION] * 3)
    left, right = tmp_path / "sequential", tmp_path / "parallel"
    assert build_library([spec], left, workers=1) == build_library([spec], right, workers=2)
    assert (left / "reactions.sqlite3").read_bytes() == (right / "reactions.sqlite3").read_bytes()


def test_source_mapping_errors_are_visible_without_fabricating_chemical_rejection():
    record = parse_patent_line(b"[CH3:1]O>>[NH2:1]O\tUS-fixture\t1\t2000\n")
    assert record["mapping_status"] == "fail"
    assert record["mapping_reason"] == "mapped_element_or_isotope_mismatch"


def test_hash_collisions_do_not_merge_reaction_counts_or_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("chemlab.evidence.reaction_library.digest", lambda value: "0" * 64)
    _, manifest, index = library(tmp_path, [OXIDATION, b"C>>CC\tUS-fixture\t1\t2000\n"])
    assert manifest["counts"]["unique_reactions"] == 2
    result = index.lookup("CC=O", ("CCO",))
    assert result["total_matches"] == 1
    assert result["matches"][0]["record"]["product"] == "CC=O"


def test_batch_index_keeps_full_identities_and_refuses_hash_aliasing(monkeypatch):
    queries = [
        {"product": "O=CC", "precursors": ["OCC"]},
        {"product": "CC=O", "precursors": ["CCO"]},
    ]
    indexed = index_reaction_inputs(queries)
    assert list(indexed.values()) == [{"product": "CC=O", "precursors": ["CCO"]}]
    monkeypatch.setattr("chemlab.evidence.reaction_library.digest", lambda value: "0" * 64)
    assert len(index_reaction_inputs(queries)) == 1
    with pytest.raises(IntegrityError, match="Different full reaction identities"):
        index_reaction_inputs([queries[0], {"product": "CNC", "precursors": ["CN", "C"]}])


def test_relative_library_paths_work_at_the_cli_boundary(tmp_path, monkeypatch):
    root, _, _ = library(tmp_path, [OXIDATION])
    monkeypatch.chdir(tmp_path)
    from pathlib import Path

    index = ReactionLibrary(Path("library"), file_digest(root / "manifest.json"))
    assert index.lookup("CC=O", ("CCO",))["status"] == "reported_match"


def test_materialized_index_has_identical_bytes_claims_and_references(tmp_path):
    root, _, original = library(tmp_path, [OXIDATION, OXIDATION])
    destination = tmp_path / "private-index-copy"
    materialize_snapshot(root, original.manifest_ref, destination, "reactions.sqlite3")
    copied = ReactionLibrary(destination, original.manifest_ref)
    assert copied.lookup("CC=O", ("CCO",)) == original.lookup("CC=O", ("CCO",))
    for name in ("reactions.sqlite3", "manifest.json", "complete.json"):
        assert (destination / name).read_bytes() == (root / name).read_bytes()
    with pytest.raises(FileExistsError):
        materialize_snapshot(root, original.manifest_ref, destination, "reactions.sqlite3")


def test_corrupt_copy_source_cannot_publish_a_completion_marker(tmp_path):
    root, _, original = library(tmp_path, [OXIDATION])
    (root / "reactions.sqlite3").write_bytes(b"corrupt source")
    destination = tmp_path / "incomplete-copy"
    with pytest.raises(IntegrityError, match="Copied index"):
        materialize_snapshot(root, original.manifest_ref, destination, "reactions.sqlite3")
    assert not (destination / "complete.json").exists()
    assert (root / "reactions.sqlite3").read_bytes() == b"corrupt source"


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_unhashed_sqlite_sidecars_cannot_supply_immutable_evidence(tmp_path, suffix):
    root, _, index = library(tmp_path, [OXIDATION])
    database = root / "reactions.sqlite3"
    database.with_name(database.name + suffix).write_bytes(b"unhashed transactional state")
    with pytest.raises(IntegrityError, match="sidecar"):
        index.lookup("CC=O", ("CCO",))


@pytest.mark.parametrize("change", ["identity", "final_reference", "source_kind"])
def test_loader_checks_declared_identity_and_evidence_partition_independently(tmp_path, change):
    root, manifest, _ = library(tmp_path, [OXIDATION])
    if change == "identity":
        manifest["identity"] = "unauthorized_policy"
    elif change == "final_reference":
        manifest["sources"][0]["partition"] = "final_reference"
    else:
        manifest["sources"][0]["kind"] = "model_suggestion"
    (root / "manifest.json").write_bytes(canonical_bytes(manifest))
    expected = file_digest(root / "manifest.json")
    (root / "complete.json").write_bytes(canonical_bytes({"manifest_sha256": expected}))
    with pytest.raises(IntegrityError, match="identity policy|partition or source kind"):
        ReactionLibrary(root, expected)


def test_query_does_not_accept_a_reaction_attributed_to_an_undeclared_source(tmp_path):
    root, manifest, _ = library(tmp_path, [OXIDATION])
    with sqlite3.connect(root / "reactions.sqlite3") as conn:
        conn.execute("UPDATE records SET source='undeclared-source'")
    manifest["database_sha256"] = file_digest(root / "reactions.sqlite3")
    (root / "manifest.json").write_bytes(canonical_bytes(manifest))
    expected = file_digest(root / "manifest.json")
    (root / "complete.json").write_bytes(canonical_bytes({"manifest_sha256": expected}))
    index = ReactionLibrary(root, expected)
    with pytest.raises(IntegrityError, match="no declared source"):
        index.lookup("CC=O", ("CCO",))
