"""Immutable, source-bound lookup of represented patent reactions."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from copy import copy
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Any

from rdkit import rdBase

from chemlab.chemistry import require_molecule
from chemlab.chemistry.identity import mapping_status
from chemlab.records import canonical_bytes, digest
from chemlab.store import IntegrityError

VERSION = "reported-reaction-library-v1"
HEADER = "ReactionSmiles\tPatentNumber\tParagraphNum\tYear\tTextMinedYield\tCalculatedYield"


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _source_integrity(path: Path, expected: str, message: str) -> None:
    if file_digest(path) != expected:
        raise IntegrityError(message)


def immutable_database_uri(path: Path) -> str:
    if any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise IntegrityError("Published reaction indexes cannot have SQLite sidecar state")
    return path.as_uri() + "?mode=ro&immutable=1"


def materialize_snapshot(
    source: Path, manifest_hash: str, destination: Path, database: str
) -> None:
    if database not in ("reactions.sqlite3", "contexts.sqlite3"):
        raise ValueError("Unsupported reaction index database")
    if destination.exists():
        raise FileExistsError("Index copies never replace existing data")
    manifest_bytes = (source / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_hash:
        raise IntegrityError("Source snapshot manifest hash mismatch")
    marker = canonical_bytes({"manifest_sha256": manifest_hash})
    if (source / "complete.json").read_bytes() != marker:
        raise IntegrityError("Only complete snapshots may be materialized")
    expected = json.loads(manifest_bytes)["database_sha256"]
    destination.mkdir(parents=True)
    copied = hashlib.sha256()
    with (
        (source / database).open("rb") as incoming,
        (destination / database).open("xb") as outgoing,
    ):
        while block := incoming.read(1024 * 1024):
            outgoing.write(block)
            copied.update(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    if copied.hexdigest() != expected or file_digest(destination / database) != expected:
        raise IntegrityError("Copied index bytes differ from the pinned snapshot")
    (destination / "manifest.json").write_bytes(manifest_bytes)
    partial = destination / "complete.json.partial"
    with partial.open("xb") as stream:
        stream.write(marker)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(partial, destination / "complete.json")


@lru_cache(maxsize=65536)
def stable_identity(smiles: str) -> str:
    identity = require_molecule(smiles).canonical_smiles
    if require_molecule(identity).canonical_smiles != identity:
        raise ValueError("identity_v1_not_idempotent_under_pinned_rdkit")
    return identity


def reaction_input(product: str, precursors: tuple[str, ...]) -> dict[str, Any]:
    if not precursors:
        raise ValueError("A reaction requires listed precursors")
    return {
        "product": stable_identity(product),
        "precursors": sorted(stable_identity(s) for s in precursors),
    }


def index_reaction_inputs(queries) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for item in queries:
        query = reaction_input(item["product"], tuple(item["precursors"]))
        key = digest(query)
        if key in indexed and indexed[key] != query:
            raise IntegrityError("Different full reaction identities have the same index hash")
        indexed[key] = query
    return indexed


def parse_patent_line(raw: bytes) -> dict[str, Any]:
    row = next(csv.reader([raw.decode("utf-8").rstrip("\r\n")], delimiter="\t"))
    if not 4 <= len(row) <= 6 or not row[1].strip():
        raise ValueError("Malformed patent source row")
    reaction = row[0]
    if "|" in reaction:
        raise ValueError("CX reaction metadata outside identity-v1 source scope")
    left, agents, product = reaction.split(">")
    normalized = reaction_input(product, tuple(left.split(".")))
    status, reason = mapping_status(left + ">>" + product)
    return {
        **normalized,
        "key": digest(normalized),
        "patent": row[1],
        "paragraph": row[2],
        "year": row[3],
        "agents": agents,
        "mapped_reaction": left + ">>" + product,
        "mapping_status": status,
        "mapping_reason": reason,
    }


def _parse_batch(rows: list[tuple[int, bytes]]) -> list[tuple[int, bytes, dict | None, str | None]]:
    parsed: list[tuple[int, bytes, dict | None, str | None]] = []
    for number, raw in rows:
        try:
            parsed.append((number, raw, parse_patent_line(raw), None))
        except Exception as exc:
            parsed.append((number, raw, None, str(exc)))
    return parsed


def build_library(
    sources: list[dict[str, Any]],
    output: Path,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    """Preserve every raw row, including rejected rows and duplicate claims."""
    if output.exists():
        raise FileExistsError("Reaction libraries are immutable; choose a new directory")
    if not 1 <= workers <= 8:
        raise ValueError("Source parsing workers must be between 1 and 8")
    if not sources or len({s["id"] for s in sources}) != len(sources):
        raise ValueError("Sources require unique IDs")
    checked = []
    for source in sources:
        if source.get("kind") != "reported_patent" or source.get("partition") != "training":
            raise ValueError("Only declared reported-patent training sources may enter this index")
        path = Path(source["path"])
        _source_integrity(
            path, source["sha256"], "Source file hash differs from pinned specification"
        )
        checked.append({**source, "bytes": path.stat().st_size})
    output.mkdir(parents=True)
    database = output / "reactions.sqlite3"
    counts: Counter = Counter()
    errors: Counter = Counter()
    with ProcessPoolExecutor(max_workers=workers) as pool, sqlite3.connect(database) as conn:
        conn.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE records (
                source TEXT NOT NULL, row_number INTEGER NOT NULL, raw BLOB NOT NULL,
                reaction_key TEXT, product TEXT, precursors TEXT, payload TEXT, error TEXT,
                PRIMARY KEY(source,row_number));
        """)
        for source in checked:
            with Path(source["path"]).open("rb") as stream:
                if stream.readline().decode("utf-8").rstrip("\r\n") != HEADER:
                    raise ValueError("Unexpected patent source header")
                rows = enumerate(stream, 1)
                while batch := list(islice(rows, 1024 * workers)):
                    groups = [batch[i : i + 1024] for i in range(0, len(batch), 1024)]
                    for parsed in pool.map(_parse_batch, groups):
                        for number, raw, record, error in parsed:
                            counts["input_rows"] += 1
                            if record is None:
                                assert error is not None
                                errors[error.split(":")[0]] += 1
                                conn.execute(
                                    "INSERT INTO records VALUES (?,?,?,NULL,NULL,NULL,NULL,?)",
                                    (source["id"], number, raw, error),
                                )
                                counts["quarantined_rows"] += 1
                            else:
                                conn.execute(
                                    "INSERT INTO records VALUES (?,?,?,?,?,?,?,NULL)",
                                    (
                                        source["id"],
                                        number,
                                        raw,
                                        record["key"],
                                        record["product"],
                                        canonical_bytes(record["precursors"]).decode("ascii"),
                                        canonical_bytes(record).decode("ascii"),
                                    ),
                                )
                                counts["accepted_rows"] += 1
                                counts["mapping_" + record["mapping_status"]] += 1
                    conn.commit()
                    if progress:
                        progress(dict(counts))
            _source_integrity(
                Path(source["path"]), source["sha256"], "Source changed during ingestion"
            )
        conn.execute("CREATE INDEX product_index ON records(product)")
        conn.execute("CREATE INDEX reaction_index ON records(reaction_key)")
        counts["unique_reactions"] = conn.execute(
            "SELECT count(*) FROM (SELECT product,precursors FROM records "
            "WHERE error IS NULL GROUP BY product,precursors)"
        ).fetchone()[0]
        conn.commit()
    manifest = {
        "version": VERSION,
        "identity": "identity-v1",
        "rdkit": rdBase.rdkitVersion,
        "sources": checked,
        "counts": dict(counts),
        "quarantine_reasons": dict(errors),
        "database_sha256": file_digest(database),
        "limitations": (
            "Patent-extracted reported reactions; not independent experimental validation"
        ),
    }
    data = canonical_bytes(manifest)
    with (output / "manifest.json").open("xb") as stream:
        stream.write(data)
    with (output / "complete.json.partial").open("xb") as stream:
        stream.write(canonical_bytes({"manifest_sha256": hashlib.sha256(data).hexdigest()}))
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(output / "complete.json.partial", output / "complete.json")
    return manifest


class ReactionLibrary:
    def __init__(self, root: Path, expected_manifest: str):
        root = root.resolve()
        self.root = root
        data = (root / "manifest.json").read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_manifest:
            raise IntegrityError("Reaction library manifest hash mismatch")
        if json.loads((root / "complete.json").read_bytes()) != {"manifest_sha256": actual}:
            raise IntegrityError("Reaction library is not completely published")
        self.manifest = json.loads(data)
        if self.manifest.get("identity") != "identity-v1":
            raise IntegrityError("Reaction library identity policy differs")
        sources = self.manifest.get("sources", [])
        if not sources or any(
            s.get("kind") != "reported_patent" or s.get("partition") != "training" for s in sources
        ):
            raise IntegrityError("Reaction library evidence partition or source kind is forbidden")
        if len({s["id"] for s in sources}) != len(sources):
            raise IntegrityError("Reaction library source IDs are ambiguous")
        if self.manifest["version"] != VERSION or self.manifest["rdkit"] != rdBase.rdkitVersion:
            raise IntegrityError("Reaction library runtime or schema differs")
        database = root / "reactions.sqlite3"
        immutable_database_uri(database)
        if file_digest(database) != self.manifest["database_sha256"]:
            raise IntegrityError("Reaction library database hash mismatch")
        self.database = database
        self.manifest_ref = actual
        self.source_ids = frozenset(s["id"] for s in sources)
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def session(self):
        if self._connection is not None:
            raise ValueError("Evidence sessions cannot be nested")
        expected = self.manifest["database_sha256"]
        if file_digest(self.database) != expected:
            raise IntegrityError("Reaction library changed after opening")
        conn = sqlite3.connect(immutable_database_uri(self.database), uri=True)
        try:
            conn.execute("BEGIN")
            snapshot = copy(self)
            snapshot._connection = conn
            yield snapshot
            if file_digest(self.database) != expected:
                raise IntegrityError("Reaction library changed during evidence batch")
        finally:
            conn.close()

    @contextmanager
    def _reader(self):
        if self._connection is not None:
            yield self._connection
        else:
            with self.session() as snapshot:
                yield snapshot._connection

    def lookup(
        self,
        product: str,
        precursors: tuple[str, ...],
        *,
        excluded: frozenset[str] = frozenset(),
        limit: int = 100,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 1000:
            raise ValueError("Evidence limit must be between 1 and 1000")
        query = reaction_input(product, precursors)
        key = digest(query)
        if key in excluded:
            return {
                "status": "unknown",
                "reason": "final_reference_identity_excluded",
                "matches": [],
            }
        with self._reader() as conn:
            exact = (key, query["product"], canonical_bytes(query["precursors"]).decode("ascii"))
            count = conn.execute(
                "SELECT count(*) FROM records WHERE reaction_key=? AND product=? AND precursors=?",
                exact,
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT source,row_number,raw,payload FROM records "
                "WHERE reaction_key=? AND product=? AND precursors=? "
                "ORDER BY source,row_number LIMIT ?",
                (*exact, limit),
            ).fetchall()
        matches = []
        for source, number, raw, payload in rows:
            if source not in self.source_ids:
                raise IntegrityError("Reaction row has no declared source")
            record = parse_patent_line(raw)
            if record != json.loads(payload):
                raise IntegrityError("Indexed claim differs from the preserved source row")
            if record["product"] != query["product"] or record["precursors"] != query["precursors"]:
                raise IntegrityError("Index key collision or identity mismatch")
            matches.append(
                {
                    "source": source,
                    "row": number,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "raw_line": raw.decode("utf-8"),
                    "reference": "https://patents.google.com/patent/" + record["patent"],
                    "record": record,
                }
            )
        return {
            "status": "reported_match" if matches else "unknown",
            "reason": "exact_represented_participants" if matches else "no_exact_reported_match",
            "query": query,
            "library_ref": self.manifest_ref,
            "total_matches": count,
            "returned_matches": len(matches),
            "limit": limit,
            "matches": matches,
            "chemical_feasibility": "unresolved",
        }
