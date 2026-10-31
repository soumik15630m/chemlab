"""Pinned, non-overwriting distribution of complete reaction indexes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from chemlab.evidence.reaction_library import ReactionLibrary, file_digest
from chemlab.evidence.reaction_templates import ContextLibrary
from chemlab.records import canonical_bytes
from chemlab.store import IntegrityError


def export_knowledge(source: ReactionLibrary, contexts: ContextLibrary, destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError("Knowledge archives never replace existing artifacts")
    if contexts.sources.manifest_ref != source.manifest_ref:
        raise IntegrityError("Context and source indexes are not bound together")
    paths = {
        f"{kind}/{name}": root / name
        for kind, root, database in (
            ("source", source.root, "reactions.sqlite3"),
            ("contexts", contexts.database.parent, "contexts.sqlite3"),
        )
        for name in (database, "manifest.json", "complete.json")
    }
    manifest: dict[str, Any] = {
        "version": "reaction-knowledge-archive-v1",
        "source_ref": source.manifest_ref,
        "context_ref": contexts.manifest_ref,
        "source_name": source.root.name,
        "context_name": contexts.database.parent.name,
        "license": "CC0-1.0 derived patent data",
        "limitations": "Reported reactions and structural analogies; not experimental validation",
        "files": {
            name: {"sha256": file_digest(path), "bytes": path.stat().st_size}
            for name, path in paths.items()
        },
    }
    if (
        manifest["files"]["source/reactions.sqlite3"]["sha256"]
        != source.manifest["database_sha256"]
    ):
        raise IntegrityError("Source index changed before packaging")
    if (
        manifest["files"]["contexts/contexts.sqlite3"]["sha256"]
        != contexts.manifest["database_sha256"]
    ):
        raise IntegrityError("Context index changed before packaging")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".partial")
    with zipfile.ZipFile(
        partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        package = zipfile.ZipInfo("package.json", date_time=(1980, 1, 1, 0, 0, 0))
        package.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(package, canonical_bytes(manifest))
        for name, path in sorted(paths.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as incoming, archive.open(info, "w", force_zip64=True) as output:
                shutil.copyfileobj(incoming, output, length=1024 * 1024)
    if any(file_digest(path) != manifest["files"][name]["sha256"] for name, path in paths.items()):
        raise IntegrityError("Knowledge changed during packaging")
    # The same restore path validates the compressed bytes before they are published.
    with zipfile.ZipFile(partial) as archive:
        for name, expected in manifest["files"].items():
            with archive.open(name) as stream:
                checksum = hashlib.sha256()
                while block := stream.read(1024 * 1024):
                    checksum.update(block)
                if checksum.hexdigest() != expected["sha256"]:
                    raise IntegrityError("Compressed knowledge bytes failed verification")
    if os.name == "nt":
        os.rename(partial, destination)
    else:
        os.link(partial, destination)
        partial.unlink()
    return {
        "sha256": file_digest(destination),
        "bytes": destination.stat().st_size,
        "package": manifest,
    }


def restore_knowledge(archive_path: Path, expected_sha256: str, destination: Path) -> dict:
    with archive_path.open("rb") as stream:
        if stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            raise ValueError("Git LFS pointer found; run git lfs pull before restoring knowledge")
    if file_digest(archive_path) != expected_sha256:
        raise IntegrityError("Knowledge archive hash mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    staging = destination / (".knowledge-restore-" + uuid.uuid4().hex)
    staging.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        package = json.loads(archive.read("package.json"))
        if package.get("version") != "reaction-knowledge-archive-v1":
            raise IntegrityError("Unsupported knowledge archive version")
        names = archive.namelist()
        allowed = {
            f"{kind}/{name}"
            for kind, database in (
                ("source", "reactions.sqlite3"),
                ("contexts", "contexts.sqlite3"),
            )
            for name in (database, "manifest.json", "complete.json")
        }
        if (
            set(package["files"]) != allowed
            or set(names) != allowed | {"package.json"}
            or (len(names) != len(set(names)))
        ):
            raise IntegrityError("Knowledge archive members differ from the declared contract")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise IntegrityError("Unsafe knowledge archive path")
            if stat.S_ISLNK(archive.getinfo(name).external_attr >> 16):
                raise IntegrityError("Knowledge archives cannot contain symlinks")
        for name, expected in package["files"].items():
            info = archive.getinfo(name)
            if info.file_size != expected["bytes"] or not 0 <= info.file_size <= 20_000_000_000:
                raise IntegrityError("Knowledge member size differs from pinned package")
            target = staging / name
            target.parent.mkdir(exist_ok=True)
            with archive.open(name) as incoming, target.open("xb") as output:
                shutil.copyfileobj(incoming, output, length=1024 * 1024)
            if file_digest(target) != expected["sha256"]:
                raise IntegrityError("Restored knowledge member hash mismatch")
    source = ReactionLibrary(staging / "source", package["source_ref"])
    ContextLibrary(staging / "contexts", package["context_ref"], source)
    result = {}
    for kind, parent, key in (
        ("source", "libraries", "source_name"),
        ("contexts", "contexts", "context_name"),
    ):
        name = package[key]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
            raise IntegrityError("Invalid knowledge snapshot directory name")
        folder = destination / parent
        folder.mkdir(exist_ok=True)
        target = folder / name
        if target.exists():
            target = folder / (name + "-" + uuid.uuid4().hex[:12])
        os.rename(staging / kind, target)
        result[kind] = str(target)
    (staging / "package.json").write_bytes(canonical_bytes(package))
    return {
        **result,
        "source_ref": package["source_ref"],
        "context_ref": package["context_ref"],
        "archive_sha256": expected_sha256,
    }
