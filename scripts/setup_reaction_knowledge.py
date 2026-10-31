"""Prepare pinned reported-reaction knowledge and register its independent evidence provider."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from chemlab.evidence.chemical_service import KnowledgeConfig, register_knowledge
from chemlab.evidence.knowledge_distribution import restore_knowledge
from chemlab.evidence.reaction_library import ReactionLibrary, file_digest, materialize_snapshot
from chemlab.evidence.reaction_templates import ContextLibrary
from chemlab.store import Store


def publication_path(parent: Path, name: str) -> Path:
    complete = sorted(p for p in parent.glob(name + "*") if (p / "complete.json").is_file())
    if len(complete) > 1:
        if len({file_digest(p / "manifest.json") for p in complete}) != 1:
            raise ValueError("Different completed knowledge snapshots need explicit selection")
    if complete:
        return complete[0]
    candidate = parent / name
    return candidate if not candidate.exists() else parent / (name + "-" + uuid.uuid4().hex[:12])


def mapper_command(interpreter: Path) -> tuple[str, ...]:
    # Resolving a venv interpreter symlink escapes its package environment.
    return (str(interpreter.absolute()), "-m", "chemlab.evidence.mapping_worker")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=Path("var/local"))
    parser.add_argument("--data", type=Path, default=Path("var/reaction-data"))
    parser.add_argument("--mapper-python", type=Path, required=True)
    parser.add_argument("--indexes", type=Path)
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--alias", default="lowe-context-v2")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.mapper_python.is_file():
        raise FileNotFoundError("The isolated mapping interpreter is missing")
    indexes = args.indexes or Path(os.environ.get("CHEMLAB_REACTION_INDEXES", str(args.data)))
    descriptor = root / "configs/reaction-sources/knowledge-artifact.json"
    if descriptor.exists() and not any((indexes / "contexts").glob("*/complete.json")):
        artifact = json.loads(descriptor.read_bytes())
        archive = root / artifact["path"]
        if not archive.is_file():
            raise FileNotFoundError("Reaction knowledge archive is missing; run git lfs pull")
        restore_knowledge(archive, artifact["sha256"], indexes)
    library_path = publication_path(indexes / "libraries", "lowe-identity-v1-2026-10-31")
    if indexes.resolve() != args.data.resolve() and not library_path.exists():
        cached = publication_path(args.data / "libraries", "lowe-identity-v1-2026-10-31")
        if (cached / "complete.json").is_file():
            materialize_snapshot(
                cached, file_digest(cached / "manifest.json"), library_path, "reactions.sqlite3"
            )
    if not (library_path / "complete.json").exists():
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/import_reaction_library.py"),
                "--spec",
                str(root / "configs/reaction-sources/lowe.json"),
                "--data",
                str(args.data),
                "--output",
                str(library_path),
                "--workers",
                str(args.workers),
            ],
            cwd=root,
            check=True,
        )
    source_hash = file_digest(library_path / "manifest.json")
    source = ReactionLibrary(library_path, source_hash)
    expected = json.loads((root / "configs/reaction-sources/lowe.json").read_bytes())
    if {s["sha256"] for s in source.manifest["sources"]} != {
        s["extracted_sha256"] for s in expected["files"]
    }:
        raise ValueError("Completed knowledge sources differ from the pinned source specification")
    context_path = publication_path(indexes / "contexts", "lowe-rdchiral-v2-2026-10-31")
    if not (context_path / "complete.json").exists():
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/build_reaction_contexts.py"),
                str(library_path),
                source_hash,
                str(context_path),
                "--workers",
                str(args.workers),
            ],
            cwd=root,
            check=True,
        )
    context_hash = file_digest(context_path / "manifest.json")
    ContextLibrary(context_path, context_hash, source)
    mapper_manifest = root / "configs/mapping/rxnmapper.json"
    config = KnowledgeConfig(
        name="Lowe CC0 reported reactions / RDChiral context / auxiliary RXNMapper",
        source_path=str(library_path.resolve()),
        source_manifest=source_hash,
        context_path=str(context_path.resolve()),
        context_manifest=context_hash,
        mapper_command=mapper_command(args.mapper_python),
        mapper_manifest_path=str(mapper_manifest),
        mapper_manifest_hash=file_digest(mapper_manifest),
    )
    ref = register_knowledge(Store(args.store), args.alias, config)
    print(json.dumps({"alias": args.alias, "knowledge_ref": ref}), flush=True)


if __name__ == "__main__":
    main()
