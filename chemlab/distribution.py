"""Frozen runtime exports with independent hashes and non-overwriting restore."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from chemlab.reporting.bundles import read_bundle
from chemlab.store import IntegrityError, Store


def file_hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def validate_runtime(root: Path) -> dict:
    with closing(sqlite3.connect(root / "index.sqlite3")) as conn:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise IntegrityError("Runtime database integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise IntegrityError("Runtime database contains dangling references")
        if conn.execute("SELECT count(*) FROM runs WHERE state IN ('queued','running')").fetchone()[
            0
        ]:
            raise IntegrityError("Runtime snapshot contains active runs")
        refs = conn.execute("SELECT ref,kind FROM artifacts ORDER BY ref").fetchall()
        runs = conn.execute("SELECT id FROM runs WHERE state='complete' ORDER BY id").fetchall()
    store = Store(root)
    for ref, kind in refs:
        store.get(ref, kind)
    for (run_id,) in runs:
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise IntegrityError("Invalid runtime run ID")
        bundle = read_bundle(root / "bundles" / run_id)
        if bundle["run_id"] != run_id:
            raise IntegrityError("Runtime bundle belongs to another run")
    return {"artifacts": len(refs), "completed_runs": len(runs)}


def export_runtime(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError("A published runtime snapshot must never be overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chemlab-snapshot-") as temporary:
        staging = Path(temporary)
        with closing(
            sqlite3.connect((source / "index.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as original:
            with closing(sqlite3.connect(staging / "index.sqlite3")) as backup:
                original.backup(backup)
        with closing(sqlite3.connect(staging / "index.sqlite3")) as conn:
            if conn.execute(
                "SELECT count(*) FROM runs WHERE state IN ('queued','running')"
            ).fetchone()[0]:
                raise IntegrityError("Wait for active runs before exporting runtime data")
            refs = conn.execute("SELECT ref FROM artifacts ORDER BY ref").fetchall()
            runs = conn.execute("SELECT id FROM runs WHERE state='complete' ORDER BY id").fetchall()
        for (ref,) in refs:
            if not re.fullmatch(r"[0-9a-f]{64}", ref):
                raise IntegrityError("Invalid runtime artifact reference")
            target = staging / "objects" / f"{ref}.json"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source / "objects" / target.name, target)
        for (run_id,) in runs:
            if Path(run_id).name != run_id or run_id in (".", ".."):
                raise IntegrityError("Invalid runtime run ID")
            read_bundle(source / "bundles" / run_id)
            shutil.copytree(source / "bundles" / run_id, staging / "bundles" / run_id)
        counts = validate_runtime(staging)
        files = {
            path.relative_to(staging).as_posix(): {
                "sha256": file_hash(path),
                "size": path.stat().st_size,
            }
            for path in sorted(staging.rglob("*"))
            if path.is_file() and path.name not in ("index.sqlite3-wal", "index.sqlite3-shm")
        }
        manifest = {
            "schema_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "original_runtime_root": str(source),
            "path_policy": (
                "Absolute model and bundle paths preserved; original Docker mounts required"
            ),
            "counts": counts,
            "files": files,
        }
        fd, partial = tempfile.mkstemp(dir=destination.parent, suffix=".partial")
        os.close(fd)
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("snapshot.json", json.dumps(manifest, sort_keys=True, indent=2))
                for name in files:
                    archive.write(staging / name, name)
            if os.name == "nt":
                os.rename(partial, destination)
            else:
                os.link(partial, destination)
        finally:
            Path(partial).unlink(missing_ok=True)
    return {"sha256": file_hash(destination), "size": destination.stat().st_size, **manifest}


def restore_runtime(archive_path: Path, destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(
            "Restore requires a new directory; existing runtime data is preserved"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=destination.parent, prefix=".runtime-staging-"
    ) as temporary:
        staging = Path(temporary) / "runtime"
        staging.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("snapshot.json"))
            if manifest.get("schema_version") != 1:
                raise IntegrityError("Unsupported runtime snapshot schema")
            files = manifest["files"]
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != {*files, "snapshot.json"}:
                raise IntegrityError("Runtime archive has unlisted, missing or duplicate members")
            for name, expected in files.items():
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or str(path) != name
                ):
                    raise IntegrityError("Unsafe runtime archive path")
                info = archive.getinfo(name)
                if info.is_dir() or info.file_size != expected["size"]:
                    raise IntegrityError("Runtime archive file size mismatch")
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as input_file, target.open("xb") as output:
                    shutil.copyfileobj(input_file, output)
                if file_hash(target) != expected["sha256"]:
                    raise IntegrityError("Runtime archive file hash mismatch")
        counts = validate_runtime(staging)
        if counts != manifest["counts"]:
            raise IntegrityError("Runtime snapshot counts do not match verified contents")
        if destination.exists():
            raise FileExistsError("Restore destination appeared during validation")
        os.rename(staging, destination)
    return {"counts": counts, "original_runtime_root": manifest["original_runtime_root"]}
