"""Source-derived RDChiral context retrieval and exact precursor replay."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from copy import copy
from pathlib import Path
from typing import Any

from pebble import ProcessPool
from rdchiral.main import rdchiralRunText
from rdchiral.template_extractor import extract_from_reaction

from chemlab.chemistry.identity import mapping_status
from chemlab.evidence.bounded import DEADLINE_SECONDS, dependency_call, dependency_session
from chemlab.evidence.reaction_library import (
    ReactionLibrary,
    file_digest,
    immutable_database_uri,
    parse_patent_line,
    reaction_input,
)
from chemlab.records import canonical_bytes, digest
from chemlab.store import IntegrityError

VERSION = "source-template-context-v2-bounded"
SETTINGS = {"combine_enantiomers": False, "keep_mapnums": False}


def _extract_context(mapped: str, product: str, precursors: tuple[str, ...]) -> dict[str, Any]:
    status, reason = mapping_status(mapped)
    if status != "pass":
        return {"status": "unknown", "reason": reason}
    left, right = mapped.split(">>")
    query = reaction_input(product, precursors)
    bound = reaction_input(right, tuple(left.split(".")))
    if bound != query:
        return {"status": "unknown", "reason": "mapping_reaction_identity_mismatch"}
    try:
        result = extract_from_reaction({"_id": digest(query), "reactants": left, "products": right})
        if not result.get("reaction_smarts"):
            return {"status": "unknown", "reason": "no_extractable_source_template"}
        context = {
            key: result.get(key)
            for key in (
                "reaction_smarts",
                "intra_only",
                "dimer_only",
                "necessary_reagent",
            )
        }
        return {"status": "observed", "template": context, "key": digest(context)}
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def extract_context(mapped: str, product: str, precursors: tuple[str, ...]) -> dict[str, Any]:
    return dependency_call(_extract_context, (mapped, product, precursors))


def _replay_context(context: dict, product: str, precursors: tuple[str, ...]) -> dict:
    try:
        query = reaction_input(product, precursors)
        outputs = rdchiralRunText(context["reaction_smarts"], query["product"], **SETTINGS)
        normalized = [reaction_input(product, tuple(s.split(".")))["precursors"] for s in outputs]
        normalized.sort(key=canonical_bytes)
        exact = query["precursors"] in normalized
        return {
            "status": "pass" if exact else "unknown",
            "reason": "exact_precursor_replay" if exact else "no_exact_precursor_replay",
            "outputs": normalized,
            "settings": SETTINGS,
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "settings": SETTINGS}


def replay_context(context: dict, product: str, precursors: tuple[str, ...]) -> dict:
    return dependency_call(_replay_context, (context, product, precursors))


def _contexts(rows):
    output = []
    for source, number, raw in rows:
        try:
            record = parse_patent_line(raw)
            context = _extract_context(
                record["mapped_reaction"],
                record["product"],
                tuple(record["precursors"]),
            )
        except Exception as exc:
            context = {"status": "error", "reason": str(exc)}
        output.append((source, number, context))
    return output


def build_context_library(
    library: ReactionLibrary,
    output: Path,
    *,
    workers: int = 1,
    progress=None,
) -> dict:
    if output.exists():
        raise FileExistsError("Context libraries are immutable; choose a new directory")
    if not 1 <= workers <= 8:
        raise ValueError("Context workers must be between 1 and 8")
    output.mkdir(parents=True)
    database = output / "contexts.sqlite3"
    counts: Counter = Counter()
    with (
        sqlite3.connect(immutable_database_uri(library.database), uri=True) as source_db,
        sqlite3.connect(database) as conn,
        ProcessPool(max_workers=workers) as pool,
    ):
        conn.executescript("""
            CREATE TABLE contexts (source TEXT, row_number INTEGER, template_key TEXT,
                payload TEXT NOT NULL, PRIMARY KEY(source,row_number));
        """)
        cursor = source_db.execute(
            "SELECT source,row_number,raw FROM records WHERE error IS NULL "
            "ORDER BY source,row_number"
        )
        if any(
            row[0] not in library.source_ids
            for row in source_db.execute("SELECT DISTINCT source FROM records")
        ):
            raise IntegrityError("Context derivation found an undeclared source")
        while batch := cursor.fetchmany(64 * workers):
            groups = [batch[i : i + 64] for i in range(0, len(batch), 64)]
            futures = [
                pool.schedule(_contexts, args=(group,), timeout=DEADLINE_SECONDS)
                for group in groups
            ]
            for group, future in zip(groups, futures, strict=True):
                try:
                    results = future.result()
                except Exception:
                    # Retry a slow chunk per row; neighbors must not inherit its timeout.
                    singles = [
                        pool.schedule(_contexts, args=([row],), timeout=DEADLINE_SECONDS)
                        for row in group
                    ]
                    results = []
                    for row, single in zip(group, singles, strict=True):
                        try:
                            results.extend(single.result())
                        except TimeoutError:
                            results.append(
                                (
                                    row[0],
                                    row[1],
                                    {
                                        "status": "error",
                                        "reason": "dependency_operation_timeout",
                                        "timeout_seconds": DEADLINE_SECONDS,
                                    },
                                )
                            )
                        except Exception as exc:
                            results.append(
                                (
                                    row[0],
                                    row[1],
                                    {
                                        "status": "error",
                                        "reason": "dependency_worker_error",
                                        "error": str(exc),
                                    },
                                )
                            )
                for source, number, context in results:
                    counts[context["status"]] += 1
                    conn.execute(
                        "INSERT INTO contexts VALUES (?,?,?,?)",
                        (
                            source,
                            number,
                            context.get("key"),
                            canonical_bytes(context).decode("ascii"),
                        ),
                    )
            conn.commit()
            if progress:
                progress(dict(counts))
        conn.execute("CREATE INDEX context_key ON contexts(template_key)")
        counts["distinct_templates"] = conn.execute(
            "SELECT count(DISTINCT template_key) FROM contexts"
        ).fetchone()[0]
    if file_digest(library.database) != library.manifest["database_sha256"]:
        raise IntegrityError("Source index changed during context derivation")
    manifest = {
        "version": VERSION,
        "source_library_ref": library.manifest_ref,
        "rdchiral": importlib.metadata.version("rdchiral"),
        "settings": SETTINGS,
        "dependency_timeout_seconds": DEADLINE_SECONDS,
        "counts": dict(counts),
        "database_sha256": file_digest(database),
        "scope": "Extracted local transformation contexts, not chemical feasibility rules",
    }
    data = canonical_bytes(manifest)
    (output / "manifest.json").write_bytes(data)
    marker = output / "complete.json.partial"
    with marker.open("xb") as stream:
        stream.write(canonical_bytes({"manifest_sha256": hashlib.sha256(data).hexdigest()}))
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(marker, output / "complete.json")
    return manifest


class ContextLibrary:
    def __init__(self, root: Path, expected_manifest: str, sources: ReactionLibrary):
        root = root.resolve()
        data = (root / "manifest.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_manifest:
            raise IntegrityError("Context manifest hash mismatch")
        if json.loads((root / "complete.json").read_bytes()) != {
            "manifest_sha256": expected_manifest,
        }:
            raise IntegrityError("Context library is not completely published")
        self.manifest = json.loads(data)
        if self.manifest["source_library_ref"] != sources.manifest_ref:
            raise IntegrityError("Context library is bound to another source index")
        if (
            self.manifest["version"] != VERSION
            or self.manifest["rdchiral"] != (importlib.metadata.version("rdchiral"))
            or self.manifest["settings"] != SETTINGS
            or self.manifest["dependency_timeout_seconds"] != DEADLINE_SECONDS
        ):
            raise IntegrityError("Context runtime or settings differ")
        self.database = root / "contexts.sqlite3"
        immutable_database_uri(self.database)
        if file_digest(self.database) != self.manifest["database_sha256"]:
            raise IntegrityError("Context database hash mismatch")
        self.manifest_ref = expected_manifest
        self.sources = sources
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def session(self):
        if self._connection is not None:
            raise ValueError("Context evidence sessions cannot be nested")
        expected = self.manifest["database_sha256"]
        if file_digest(self.database) != expected:
            raise IntegrityError("Context database changed after opening")
        conn = sqlite3.connect(immutable_database_uri(self.database), uri=True)
        try:
            conn.execute("BEGIN")
            with self.sources.session() as sources, dependency_session():
                snapshot = copy(self)
                snapshot.sources = sources
                snapshot._connection = conn
                yield snapshot
                if file_digest(self.database) != expected:
                    raise IntegrityError("Context database changed during evidence batch")
        finally:
            conn.close()

    @contextmanager
    def _readers(self):
        if self._connection is not None:
            yield self._connection, self.sources._connection
        else:
            with self.session() as snapshot:
                yield snapshot._connection, snapshot.sources._connection

    def lookup(
        self,
        mapped: str,
        product: str,
        precursors: tuple[str, ...],
        *,
        excluded: frozenset[str] = frozenset(),
        limit: int = 100,
    ) -> dict:
        query = reaction_input(product, precursors)
        context = extract_context(mapped, product, precursors)
        if context["status"] != "observed":
            return {**context, "matches": []}
        if not 1 <= limit <= 1000:
            raise ValueError("Context evidence limit must be between 1 and 1000")
        with self._readers() as (conn, source_db):
            rows = conn.execute(
                "SELECT source,row_number,payload FROM contexts WHERE template_key=? "
                "ORDER BY source,row_number LIMIT ?",
                (context["key"], limit),
            ).fetchall()
            matches, excluded_count = [], 0
            for source, number, payload in rows:
                if source not in self.sources.source_ids:
                    raise IntegrityError("Context has no declared source")
                raw = source_db.execute(
                    "SELECT raw FROM records WHERE source=? AND row_number=?",
                    (source, number),
                ).fetchone()
                if raw is None:
                    raise IntegrityError("Context has no bound source row")
                record = parse_patent_line(raw[0])
                if record["key"] in excluded:
                    excluded_count += 1
                    continue
                reconstructed = extract_context(
                    record["mapped_reaction"],
                    record["product"],
                    tuple(record["precursors"]),
                )
                if reconstructed != json.loads(payload) or reconstructed != context:
                    raise IntegrityError(
                        "Context differs from its source or complete query context"
                    )
                replay = replay_context(reconstructed["template"], product, precursors)
                matches.append(
                    {
                        "source": source,
                        "row": number,
                        "raw_sha256": hashlib.sha256(raw[0]).hexdigest(),
                        "raw_line": raw[0].decode("utf-8"),
                        "record": record,
                        "reference": "https://patents.google.com/patent/" + record["patent"],
                        "source_reaction_key": record["key"],
                        "replay": replay,
                    }
                )
        supported = any(m["replay"]["status"] == "pass" for m in matches)
        return {
            "status": "context_replay_match" if supported else "unknown",
            "reason": "source_context_and_exact_replay"
            if supported
            else "no_complete_context_support",
            "context": context,
            "query": query,
            "matches": matches,
            "limit": limit,
            "excluded_sources": excluded_count,
            "library_ref": self.manifest_ref,
            "source_library_ref": self.sources.manifest_ref,
            "chemical_feasibility": "unresolved",
        }
