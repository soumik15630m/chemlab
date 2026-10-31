"""Import and combine stock snapshots while retaining full identity and source bytes."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from pydantic import Field, model_validator
from rdkit import rdBase

from chemlab.chemistry import require_molecule
from chemlab.records import Record, Stock, canonical_bytes
from chemlab.registry import Registry
from chemlab.store import IntegrityError, Store


class StockCSVSpec(Record):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0)
    rows: int = Field(gt=0)
    id_column: str = "bb_id"
    smiles_column: str = "smiles"
    license: str = Field(min_length=1)
    license_url: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    card_url: str = Field(min_length=1)
    card_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_columns(self):
        if not self.id_column or not self.smiles_column or self.id_column == self.smiles_column:
            raise ValueError("Stock requires distinct nonempty ID and SMILES column names")
        return self


def parse_stock_csv(raw: bytes, spec: StockCSVSpec) -> tuple[tuple[str, ...], dict[str, Any]]:
    if len(raw) != spec.size or hashlib.sha256(raw).hexdigest() != spec.sha256:
        raise IntegrityError("Stock CSV bytes differ from the pinned size or SHA-256")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")), strict=True)
    columns = reader.fieldnames or []
    if len(set(columns)) != len(columns) or not {spec.id_column, spec.smiles_column}.issubset(
        columns
    ):
        raise ValueError(
            "Stock CSV requires unambiguous ID and SMILES columns; InChIKeys alone are insufficient"
        )
    seen_ids: set[str] = set()
    identities: set[str] = set()
    quarantined = []
    total = accepted = 0
    for number, row in enumerate(reader, 1):
        total += 1
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Malformed stock CSV row {number}")
        source_id = row[spec.id_column]
        if not source_id.strip() or source_id in seen_ids:
            raise ValueError(f"Missing or duplicate stock source ID at row {number}")
        seen_ids.add(source_id)
        try:
            identity = require_molecule(row[spec.smiles_column]).canonical_smiles
            if require_molecule(identity).canonical_smiles != identity:
                raise ValueError("identity_v1_not_idempotent_under_pinned_rdkit")
            identities.add(identity)
            accepted += 1
        except ValueError as exc:
            quarantined.append({"row": number, "original": row, "error": str(exc)})
    if total != spec.rows:
        raise IntegrityError("Stock row count differs from the pinned source specification")
    if not identities:
        raise ValueError("Stock source has no supported identities")
    audit = {
        "source_sha256": spec.sha256,
        "revision": spec.revision,
        "policy_version": "stock-csv-v1",
        "identity_policy": "identity-v1",
        "rdkit_version": rdBase.rdkitVersion,
        "input_rows": total,
        "accepted_rows": accepted,
        "unique_identities": len(identities),
        "duplicate_identity_rows": accepted - len(identities),
        "quarantined": quarantined,
        "policy": (
            "Full canonical identities; preserve stereo, charge, isotopes and fragments. "
            "Quarantine unstable identities; raw IDs and duplicate rows retained in source bytes."
        ),
    }
    return tuple(sorted(identities)), audit


def register_csv_stock(
    store: Store, alias: str, raw: bytes, card: bytes, spec: StockCSVSpec
) -> dict[str, Any]:
    if hashlib.sha256(card).hexdigest() != spec.card_sha256:
        raise IntegrityError("Dataset card differs from the pinned source")
    identities, audit = parse_stock_csv(raw, spec)
    source_ref = store.put(
        "stock_csv_source",
        {
            "spec": spec.model_dump(mode="json"),
            "text": raw.decode("utf-8"),
            "dataset_card": card.decode("utf-8"),
        },
    )
    audit_ref = store.put("stock_ingestion_report", audit)
    stock = Stock(
        name=spec.name,
        source=spec.url + "; revision=" + spec.revision + "; " + spec.limitations,
        license=spec.license + "; " + spec.license_url + "; " + spec.attribution,
        identities=identities,
        source_artifact_ref=source_ref,
        ingestion_report_ref=audit_ref,
    )
    ref = store.put("stock", stock)
    Registry(store).register(alias, "stock", ref)
    return {
        "stock_ref": ref,
        "source_ref": source_ref,
        "audit_ref": audit_ref,
        "input_rows": audit["input_rows"],
        "accepted_rows": audit["accepted_rows"],
        "unique_identities": len(identities),
        "quarantined_rows": len(audit["quarantined"]),
        "license": spec.license,
        "limitations": spec.limitations,
    }


def validate_imported_stock(store: Store, stock: Stock) -> None:
    assert stock.source_artifact_ref and stock.ingestion_report_ref
    source = store.get(stock.source_artifact_ref, "stock_csv_source")
    spec = StockCSVSpec.model_validate(source["spec"])
    if hashlib.sha256(source["dataset_card"].encode("utf-8")).hexdigest() != spec.card_sha256:
        raise IntegrityError("Stored stock dataset-card bytes do not match the pinned source")
    identities, expected = parse_stock_csv(source["text"].encode("utf-8"), spec)
    audit = store.get(stock.ingestion_report_ref, "stock_ingestion_report")
    if (
        identities != stock.identities
        or audit != expected
        or stock.name != spec.name
        or stock.source != spec.url + "; revision=" + spec.revision + "; " + spec.limitations
        or stock.license != spec.license + "; " + spec.license_url + "; " + spec.attribution
    ):
        raise IntegrityError("Stock identities or audit differ from replayed source ingestion")


def merge_stocks(store: Store, aliases: list[str], alias: str) -> dict[str, Any]:
    from chemlab.evidence.checks import load_stock

    registry = Registry(store)
    refs = tuple(sorted({registry.resolve(value, "stock") for value in aliases}))
    if not refs:
        raise ValueError("At least one full-identity stock is required")
    parents = [load_stock(store, ref) for ref in refs]
    identities = tuple(sorted({identity for parent in parents for identity in parent.identities}))
    license_terms = [
        {"stock_ref": ref, "license": parent.license}
        for ref, parent in zip(refs, parents, strict=True)
    ]
    stock = Stock(
        name=alias,
        source="Exact identity-v1 union; component snapshots retained",
        license="Component terms apply separately: "
        + canonical_bytes(license_terms).decode("ascii"),
        identities=identities,
        component_refs=refs,
    )
    ref = store.put("stock", stock)
    registry.register(alias, "stock", ref)
    return {
        "stock_ref": ref,
        "component_refs": refs,
        "unique_identities": len(identities),
        "overlapping_identity_occurrences": sum(len(p.identities) for p in parents)
        - len(identities),
    }


def fetch_verified(url: str, destination: Path, sha256: str, size: int | None = None) -> bytes:
    def check(data):
        if hashlib.sha256(data).hexdigest() != sha256 or (size is not None and len(data) != size):
            raise IntegrityError("Downloaded stock source differs from pinned bytes")

    if destination.exists():
        data = destination.read_bytes()
        check(data)
        return data
    if not url.startswith("https://"):
        raise ValueError("Stock downloads require HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".partial")
    with urlopen(Request(url, headers={"User-Agent": "ChemLab/0.1"}), timeout=120) as response:
        with partial.open("xb") as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > (size if size is not None else 1024 * 1024):
                    raise IntegrityError("Stock source exceeds declared download size")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    data = partial.read_bytes()
    check(data)
    try:
        os.link(partial, destination)
    except FileExistsError:
        check(destination.read_bytes())
    partial.unlink()
    return data
