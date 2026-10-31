"""Retain exact source bindings for observed context extraction failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from chemlab.evidence.reaction_library import ReactionLibrary
from chemlab.records import canonical_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("source_hash")
    parser.add_argument("contexts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Failure audits are immutable")
    source = ReactionLibrary(args.source, args.source_hash)
    failures = []
    with (
        sqlite3.connect(
            (args.contexts / "contexts.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
        ) as conn,
        sqlite3.connect(source.database.as_uri() + "?mode=ro&immutable=1", uri=True) as original,
    ):
        for dataset, number, payload in conn.execute(
            "SELECT source,row_number,payload FROM contexts WHERE template_key IS NULL "
            "ORDER BY source,row_number"
        ):
            result = json.loads(payload)
            if result["status"] != "error":
                continue
            raw = original.execute(
                "SELECT raw FROM records WHERE source=? AND row_number=?", (dataset, number)
            ).fetchone()[0]
            failures.append(
                {
                    "source": dataset,
                    "row": number,
                    "raw_line": raw.decode(),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "result": result,
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        canonical_bytes(
            {
                "source_ref": source.manifest_ref,
                "failures": failures,
                "scope": "Observed software extraction failures; not chemical invalidity judgments",
            }
        )
    )
    print(json.dumps({"observed_extraction_errors": len(failures)}), flush=True)


if __name__ == "__main__":
    main()
