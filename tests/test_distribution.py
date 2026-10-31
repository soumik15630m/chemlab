import json
import sqlite3
import zipfile

import pytest

from chemlab.application import Application
from chemlab.distribution import export_runtime, restore_runtime
from chemlab.store import IntegrityError
from scripts.fetch_pretrained import require_materialized


def test_snapshot_restores_registry_objects_and_complete_bundles(lab, tmp_path):
    store, config, *_ = lab
    app = Application(store)
    run_id = app.prepare("CCOC(C)=O", config)
    app.execute(run_id)
    assert app.run(run_id)["state"] == "complete"
    archive = tmp_path / "runtime.zip"
    result = export_runtime(store.root, archive)
    assert result["counts"]["completed_runs"] == 1
    with zipfile.ZipFile(archive) as source:
        assert f"bundles/{run_id}/complete.json" in source.namelist()
        assert "index.sqlite3-wal" not in source.namelist()
        assert "index.sqlite3-shm" not in source.namelist()
    restored = tmp_path / "restored"
    summary = restore_runtime(archive, restored)
    assert summary["counts"] == result["counts"]
    assert (restored / "objects" / f"{config.stock_ref}.json").read_bytes() == (
        store.objects / f"{config.stock_ref}.json"
    ).read_bytes()
    with sqlite3.connect(restored / "index.sqlite3") as conn:
        assert conn.execute("SELECT id,state FROM runs").fetchall() == [(run_id, "complete")]


def test_active_run_cannot_be_published_as_snapshot(lab, tmp_path):
    store, config, *_ = lab
    Application(store).prepare("CCOC(C)=O", config)
    destination = tmp_path / "runtime.zip"
    with pytest.raises(IntegrityError, match="active runs"):
        export_runtime(store.root, destination)
    assert not destination.exists()


def test_active_chemical_job_cannot_be_published_as_runtime_snapshot(lab, tmp_path):
    from chemlab.evidence.chemical_service import ChemicalService, parse_reaction

    store, *_ = lab
    service = ChemicalService(store)
    job_id = service.prepare([parse_reaction("CCO>>CC=O")], None)
    destination = tmp_path / "active-chemistry.zip"
    with pytest.raises(IntegrityError, match="active chemical"):
        export_runtime(store.root, destination)
    assert not destination.exists()
    service.execute(job_id)
    completed = tmp_path / "completed-chemistry.zip"
    export_runtime(store.root, completed)
    restored = tmp_path / "restored-chemistry"
    restore_runtime(completed, restored)
    assert ChemicalService(type(store)(restored)).job(job_id) == service.job(job_id)


def test_corrupt_registered_object_blocks_export(lab, tmp_path):
    store, config, *_ = lab
    (store.objects / f"{config.stock_ref}.json").write_bytes(b"{}")
    destination = tmp_path / "runtime.zip"
    with pytest.raises(IntegrityError, match="hash mismatch"):
        export_runtime(store.root, destination)
    assert not destination.exists()


def test_existing_snapshot_and_runtime_are_never_overwritten(lab, tmp_path):
    store, *_ = lab
    destination = tmp_path / "existing.zip"
    destination.write_bytes(b"existing artifact")
    with pytest.raises(FileExistsError):
        export_runtime(store.root, destination)
    assert destination.read_bytes() == b"existing artifact"
    existing = tmp_path / "state"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_bytes(b"existing work")
    with pytest.raises(FileExistsError):
        restore_runtime(destination, existing)
    assert marker.read_bytes() == b"existing work"


@pytest.mark.parametrize("name", ["../escaped.txt", "/tmp/escaped.txt", "C:/escaped.txt", "a\\b"])
def test_archive_paths_cannot_escape_staging(tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    manifest = {"schema_version": 1, "files": {name: {"sha256": "unused", "size": 4}}}
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("snapshot.json", json.dumps(manifest))
        output.writestr(name, b"evil")
    destination = tmp_path / "restored"
    with pytest.raises(IntegrityError, match="Unsafe runtime archive path"):
        restore_runtime(archive, destination)
    assert not destination.exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_modified_archive_fails_before_publication(lab, tmp_path):
    store, *_ = lab
    original = tmp_path / "original.zip"
    export_runtime(store.root, original)
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(corrupt, "w") as output:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "index.sqlite3":
                data = b"!" + data[1:]
            output.writestr(item.filename, data)
    destination = tmp_path / "restored"
    with pytest.raises(IntegrityError, match="file hash mismatch"):
        restore_runtime(corrupt, destination)
    assert not destination.exists()


def test_lfs_pointer_is_not_a_model_checkpoint(tmp_path):
    directory = tmp_path / "generator"
    directory.mkdir()
    (directory / "combined.ckpt").write_bytes(
        b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 123\n"
    )
    with pytest.raises(ValueError, match="git lfs pull"):
        require_materialized(directory)
    (directory / "combined.ckpt").write_bytes(b"materialized fixture bytes")
    require_materialized(directory)
