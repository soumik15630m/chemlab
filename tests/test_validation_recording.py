import hashlib
import json
import subprocess

import pytest

from scripts import record_validation


def test_validation_cannot_certify_source_edited_after_its_checks(monkeypatch, tmp_path):
    script = tmp_path / "scripts/record_validation.py"
    script.parent.mkdir()
    script.write_text("software fixture")
    code = tmp_path / "chemlab/core.py"
    code.parent.mkdir()
    code.write_bytes(b"original implementation")
    monkeypatch.setattr(record_validation, "__file__", str(script))

    def execute(command, **kwargs):
        code.write_bytes(b"changed after checks began")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(record_validation.subprocess, "run", execute)
    output = tmp_path / "report"
    assert record_validation.main(output) == 1
    report = json.loads((output / "validation.json").read_bytes())
    assert report["passed"] is False
    assert report["source_changes_during_validation"] == ["chemlab/core.py"]
    assert (
        report["initial_source_hashes"]["chemlab/core.py"]
        == hashlib.sha256(b"original implementation").hexdigest()
    )
    assert (
        report["source_hashes"]["chemlab/core.py"]
        == hashlib.sha256(b"changed after checks began").hexdigest()
    )
    with pytest.raises(FileExistsError):
        record_validation.main(output)


def test_unchanged_sources_can_complete_validation_and_timeout_cannot_pass(monkeypatch, tmp_path):
    script = tmp_path / "scripts/record_validation.py"
    script.parent.mkdir()
    script.write_text("software fixture")
    monkeypatch.setattr(record_validation, "__file__", str(script))
    monkeypatch.setattr(
        record_validation.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, "", ""),
    )
    assert record_validation.main(tmp_path / "success") == 0

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 600)

    monkeypatch.setattr(record_validation.subprocess, "run", timeout)
    assert record_validation.main(tmp_path / "timeout") == 1
    report = json.loads((tmp_path / "timeout/validation.json").read_bytes())
    assert report["passed"] is False
    assert report["commands"][0]["returncode"] == 124
