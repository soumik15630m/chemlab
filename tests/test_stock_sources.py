import hashlib
import json
from pathlib import Path

import pytest

from chemlab.evidence.checks import import_stock, load_stock
from chemlab.evidence.stock_sources import (
    StockCSVSpec,
    fetch_verified,
    merge_stocks,
    parse_stock_csv,
    register_csv_stock,
)
from chemlab.records import Stock, canonical_bytes
from chemlab.registry import Registry
from chemlab.reporting.bundles import read_bundle, references
from chemlab.store import IntegrityError, Store

CARD = b"Constructed stock source for boundary tests; not a commercial catalogue."


def specification(raw: bytes, rows: int) -> StockCSVSpec:
    return StockCSVSpec(
        name="Stock contract fixture",
        url="https://example.invalid/stock.csv",
        revision="fixture-1",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        rows=rows,
        license="CC-BY-NC-SA-4.0",
        license_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        attribution="Constructed fixture",
        card_url="https://example.invalid/card",
        card_sha256=hashlib.sha256(CARD).hexdigest(),
        limitations="Snapshot membership only",
    )


def test_csv_import_keeps_full_identity_and_duplicate_source_records(tmp_path):
    raw = (
        b"bb_id,smiles\n1,C[C@H](O)F\n2,C[C@@H](O)F\n3,[13CH3]O\n4,CO\n"
        b"5,[Na+].CC(=O)[O-]\n6,CC(=O)O\n7,OCC\n8,CCO\n9,invalid\n"
    )
    spec = specification(raw, 9)
    store = Store(tmp_path)
    result = register_csv_stock(store, "fixture", raw, CARD, spec)
    stock = load_stock(store, result["stock_ref"])
    assert set(stock.identities) == {
        "C[C@H](O)F",
        "C[C@@H](O)F",
        "[13CH3]O",
        "CO",
        "CC(=O)[O-].[Na+]",
        "CC(=O)O",
        "CCO",
    }
    source = store.get(result["source_ref"], "stock_csv_source")
    assert source["text"].encode("utf-8") == raw
    assert source["dataset_card"].encode("utf-8") == CARD
    audit = store.get(result["audit_ref"], "stock_ingestion_report")
    assert (
        audit["input_rows"],
        audit["accepted_rows"],
        audit["unique_identities"],
        audit["duplicate_identity_rows"],
    ) == (9, 8, 7, 1)
    assert audit["quarantined"][0]["original"] == {"bb_id": "9", "smiles": "invalid"}
    assert result["quarantined_rows"] == 1
    assert "CC-BY-NC-SA-4.0" in stock.license
    assert references("stock", stock.model_dump(mode="json")) == {
        result["source_ref"],
        result["audit_ref"],
    }


def test_legacy_stock_encoding_and_alias_are_unchanged(tmp_path):
    stock = Stock(name="Legacy", source="test", license="test", identities=("CCO",))
    assert (
        canonical_bytes(stock) == b'{"identities":["CCO"],"license":"test","name":"Legacy",'
        b'"schema_version":1,"source":"test"}'
    )
    store = Store(tmp_path)
    before = import_stock(store, ["CCO"], "Legacy", "test", "test")
    Registry(store).register("legacy", "stock", before)
    after = import_stock(store, ["OCC"], "Legacy", "test", "test")
    assert before == after
    Registry(store).register("legacy", "stock", after)


@pytest.mark.parametrize(
    "raw,rows",
    [
        (b"bb_id,smiles\n1,CCO\n1,C\n", 2),
        (b"bb_id,smiles\n,CCO\n", 1),
        (b"bb_id,smiles\n1,CCO,extra\n", 1),
        (b"bb_id,smiles\n1\n", 1),
        (b"bb_id,smiles,smiles\n1,CCO,C\n", 1),
        (b"inchi_key\nLFQSCWFLJHTTHZ-UHFFFAOYSA-N\n", 1),
        (b"bb_id,smiles\n1,*\n", 1),
    ],
)
def test_malformed_or_key_only_stocks_are_not_admitted(raw, rows):
    with pytest.raises(ValueError):
        parse_stock_csv(raw, specification(raw, rows))


def test_pinned_source_mismatch_row_count_and_card_are_rejected(tmp_path):
    raw = b"bb_id,smiles\n1,CCO\n"
    spec = specification(raw, 1)
    with pytest.raises(IntegrityError, match="bytes"):
        parse_stock_csv(raw + b"\n", spec)
    with pytest.raises(IntegrityError, match="bytes"):
        parse_stock_csv(raw.replace(b"CCO", b"CCC"), spec)
    with pytest.raises(IntegrityError, match="row count"):
        parse_stock_csv(raw, spec.model_copy(update={"rows": 2}))
    store = Store(tmp_path)
    with pytest.raises(IntegrityError, match="card"):
        register_csv_stock(store, "invalid", raw, b"other terms", spec)
    assert Registry(store).list() == []


def test_imported_stock_replays_source_and_does_not_allow_relabelling(tmp_path):
    raw = b"bb_id,smiles\n1,CCO\n"
    store = Store(tmp_path)
    result = register_csv_stock(store, "fixture", raw, CARD, specification(raw, 1))
    stock = load_stock(store, result["stock_ref"])
    for changed in ({"identities": ("C",)}, {"license": "Apache-2.0"}):
        ref = store.put("stock", stock.model_copy(update=changed))
        with pytest.raises(IntegrityError, match="replayed"):
            load_stock(store, ref)
    (store.objects / f"{result['source_ref']}.json").write_bytes(b"{}")
    with pytest.raises(IntegrityError, match="hash"):
        load_stock(store, result["stock_ref"])


def test_union_is_exact_order_independent_and_retains_component_terms(tmp_path):
    store = Store(tmp_path)
    registry = Registry(store)
    a = import_stock(store, ["CO", "C[C@H](O)F"], "a", "fixture", "terms-a")
    b = import_stock(store, ["CO", "C[C@@H](O)F"], "b", "fixture", "terms-b")
    registry.register("a", "stock", a)
    registry.register("b", "stock", b)
    first = merge_stocks(store, ["a", "b", "a"], "combined")
    second = merge_stocks(store, ["b", "a"], "combined")
    assert first == second
    combined = load_stock(store, first["stock_ref"])
    assert set(combined.identities) == {"CO", "C[C@H](O)F", "C[C@@H](O)F"}
    assert first["overlapping_identity_occurrences"] == 1
    assert "terms-a" in combined.license and "terms-b" in combined.license
    assert references("stock", combined.model_dump(mode="json")) == {a, b}
    for changed in (
        {"identities": ("CO",)},
        {"identities": (*combined.identities, "C")},
        {"license": "Apache-2.0"},
    ):
        ref = store.put("stock", combined.model_copy(update=changed))
        with pytest.raises(ValueError, match="union"):
            load_stock(store, ref)
    assert registry.resolve("a", "stock") == a


def test_stock_sources_and_union_components_are_in_complete_bundles(lab):
    from chemlab.application import Application

    store, config, *_ = lab
    raw = b"bb_id,smiles\n1,CCO\n"
    imported = register_csv_stock(store, "csv", raw, CARD, specification(raw, 1))
    registry = Registry(store)
    registry.register("baseline", "stock", config.stock_ref)
    merged = merge_stocks(store, ["baseline", "csv"], "combined")
    app = Application(store)
    run_id = app.prepare("CCOC(C)=O", config.model_copy(update={"stock_ref": merged["stock_ref"]}))
    app.execute(run_id)
    row = app.run(run_id)
    assert row["state"] == "complete", row["error"]
    bundle = read_bundle(row["bundle"])
    assert {
        imported["source_ref"],
        imported["audit_ref"],
        imported["stock_ref"],
        config.stock_ref,
    }.issubset(bundle["objects"])
    assert len(bundle["groups"]["verified_consistent"]) == 1
    (Path(row["bundle"]) / "objects" / f"{imported['source_ref']}.json").write_bytes(b"{}")
    with pytest.raises(IntegrityError, match="hash"):
        read_bundle(row["bundle"])


def test_verified_download_reuses_matching_bytes_and_preserves_bad_existing_files(
    tmp_path, monkeypatch
):
    import chemlab.evidence.stock_sources as sources

    raw = b"bb_id,smiles\n1,CCO\n"
    spec = specification(raw, 1)
    path = tmp_path / "stock.csv"

    class Response:
        def __enter__(self):
            import io

            self.stream = io.BytesIO(raw)
            return self.stream

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(sources, "urlopen", lambda *args, **kwargs: Response())
    assert fetch_verified(spec.url, path, spec.sha256, spec.size) == raw
    monkeypatch.setattr(
        sources,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("Matching file was downloaded again"),
    )
    assert fetch_verified(spec.url, path, spec.sha256, spec.size) == raw
    path.write_bytes(b"existing data")
    with pytest.raises(IntegrityError, match="pinned"):
        fetch_verified(spec.url, path, spec.sha256, spec.size)
    assert path.read_bytes() == b"existing data"


@pytest.mark.parametrize("failure", ["checksum", "interrupted"])
def test_failed_download_does_not_publish_a_completed_source(tmp_path, monkeypatch, failure):
    import io

    import chemlab.evidence.stock_sources as sources

    expected = b"bb_id,smiles\n1,CCO\n"
    wrong = expected.replace(b"CCO", b"CCC")
    spec = specification(expected, 1)
    destination = tmp_path / "stock.csv"

    class Response:
        def __enter__(self):
            self.calls = 0
            self.stream = io.BytesIO(wrong)
            return self

        def read(self, size):
            self.calls += 1
            if failure == "interrupted" and self.calls == 2:
                raise OSError("Injected connection interruption")
            return self.stream.read(size)

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(sources, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises((IntegrityError, OSError)):
        fetch_verified(spec.url, destination, spec.sha256, spec.size)
    assert not destination.exists()
    assert len(list(tmp_path.glob("*.partial"))) == 1


def test_actual_ursa_stereo_identity_cycle_is_quarantined_without_rewriting():
    from chemlab.chemistry import require_molecule

    original = "O[C@H]1C2OC3OC1[C@@H](O)[C@H](O3)[C@@H]2O"
    first = "O[C@H]1C2OC3OC1[C@H](O)[C@H](O3)[C@H]2O"
    second = "O[C@H]1C2OC3OC1[C@@H](O)[C@H](O3)[C@@H]2O"
    assert require_molecule(original).canonical_smiles == first
    assert require_molecule(first).canonical_smiles == second
    assert require_molecule(second).canonical_smiles == first
    raw = f"bb_id,smiles\nURSA-BB-223298,{original}\npositive,CCO\n".encode("ascii")
    identities, audit = parse_stock_csv(raw, specification(raw, 2))
    assert identities == ("CCO",)
    assert audit["accepted_rows"] == 1
    assert audit["quarantined"] == [
        {
            "row": 1,
            "original": {"bb_id": "URSA-BB-223298", "smiles": original},
            "error": "identity_v1_not_idempotent_under_pinned_rdkit",
        }
    ]


def test_ursa_manifest_is_pinned_and_separately_licensed():
    path = Path(__file__).resolve().parents[1] / "configs/stocks/ursa-bbs-v1.json"
    spec = StockCSVSpec.model_validate(json.loads(path.read_text(encoding="ascii")))
    assert spec.revision == "66a64e2e375dde30941770e831ce11ed3db91f55"
    assert spec.sha256 == "b895120f2b80a75e9208b969dd6d4d453196bda231649824f9a5d33bb53ad3e6"
    assert spec.rows == 255958 and spec.size == 10955751
    assert spec.license == "CC-BY-NC-SA-4.0"
