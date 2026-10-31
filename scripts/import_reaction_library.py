"""Fetch the pinned CC0 Lowe corpus and publish a source-bound reaction index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import py7zr
from rdkit import RDLogger

from chemlab.evidence.reaction_library import build_library, file_digest
from chemlab.evidence.stock_sources import fetch_verified


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=Path("configs/reaction-sources/lowe.json"))
    parser.add_argument("--data", type=Path, default=Path("var/reaction-data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_bytes())
    sources = []
    for item in spec["files"]:
        archive_path = args.data / "downloads" / item["archive"]
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        fetch_verified(item["url"], archive_path, item["sha256"], item["bytes"])
        folder = args.data / "extracted" / Path(item["archive"]).stem
        if not folder.exists():
            with py7zr.SevenZipFile(archive_path) as archive:
                members = archive.list()
                if len(members) != 1 or members[0].filename != item["member"]:
                    raise ValueError("Archive members differ from the pinned source")
                if members[0].uncompressed != item["extracted_bytes"]:
                    raise ValueError("Expanded source size differs from specification")
                if Path(item["member"]).name != item["member"] or "\\" in item["member"]:
                    raise ValueError("Source member must be a plain filename")
                folder.mkdir(parents=True)
                archive.extractall(folder)
        path = folder / item["member"]
        if path.stat().st_size != item["extracted_bytes"]:
            raise ValueError("Extracted source size mismatch")
        sources.append(
            {
                "id": item["id"],
                "path": str(path.resolve()),
                "sha256": item["extracted_sha256"],
                "archive_sha256": item["sha256"],
                "url": item["url"],
                "doi": spec["doi"],
                "license": spec["license"],
                "kind": spec["kind"],
                "partition": spec["partition"],
            }
        )
    RDLogger.DisableLog("rdApp.*")
    manifest = build_library(
        sources,
        args.output,
        workers=args.workers,
        progress=lambda counts: print(json.dumps(counts), flush=True),
    )
    print(json.dumps({"manifest_sha256": file_digest(args.output / "manifest.json"), **manifest}))


if __name__ == "__main__":
    main()
