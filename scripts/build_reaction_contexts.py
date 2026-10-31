"""Derive an immutable context vocabulary from a completely published source index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rdkit import RDLogger

from chemlab.evidence.reaction_library import ReactionLibrary
from chemlab.evidence.reaction_templates import build_context_library


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest_hash")
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    RDLogger.DisableLog("rdApp.*")
    library = ReactionLibrary(args.source, args.manifest_hash)
    manifest = build_context_library(
        library,
        args.output,
        workers=args.workers,
        progress=lambda count: print(json.dumps(count), flush=True),
    )
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
