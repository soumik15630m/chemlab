"""Run validation in a disposable container and retain machine-readable evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def source_hashes(root: Path) -> dict[str, str]:
    files = {
        file
        for directory in ("chemlab", "tests", "scripts", "configs")
        for file in (root / directory).rglob("*")
        if file.is_file() and file.suffix in (".py", ".js", ".css", ".html", ".json")
    }
    files.update(
        root / name
        for name in (
            "start_venv.py",
            "start_docker.py",
            "Dockerfile",
            "compose.yaml",
            "requirements.lock",
            "requirements-mapping.lock",
        )
        if (root / name).is_file()
    )
    return {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(files)
    }


def main(destination: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    if destination.exists():
        raise FileExistsError("Validation reports are immutable; choose a new directory")
    destination.mkdir(parents=True)
    before = source_hashes(root)
    commands = [
        [
            "ruff",
            "check",
            "chemlab",
            "tests",
            "scripts",
            "start_venv.py",
            "start_docker.py",
            "--no-cache",
        ],
        [
            "ruff",
            "format",
            "--check",
            "chemlab",
            "tests",
            "scripts",
            "start_venv.py",
            "start_docker.py",
            "--no-cache",
        ],
        ["mypy", "chemlab", "--cache-dir", "/tmp/mypy-cache"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--basetemp=/tmp/contract-tests",
            "-o",
            "cache_dir=/tmp/pytest-cache",
            f"--junitxml={destination / 'contract-suite.xml'}",
        ],
        [sys.executable, "scripts/mutation_checks.py", str(destination / "mutation-report.json")],
    ]
    results = []
    for command in commands:
        try:
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "command": command,
                    "returncode": 124,
                    "stdout": "",
                    "stderr": f"Validation operation timed out: {exc}",
                }
            )
            break
        results.append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        print(result.stdout, flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
            break
    hashes = source_hashes(root)
    changed = sorted(
        name for name in before.keys() | hashes.keys() if before.get(name) != hashes.get(name)
    )
    junit = destination / "contract-suite.xml"
    counts = {}
    if junit.exists():
        suites = ET.parse(junit).getroot()
        counts = {
            key: sum(int(s.get(key, 0)) for s in suites.iter("testsuite"))
            for key in ("tests", "failures", "errors", "skipped")
        }
    report = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Local Docker computational validation",
        "passed": not changed
        and len(results) == len(commands)
        and all(r["returncode"] == 0 for r in results),
        "commands": results,
        "test_counts": counts,
        "source_hashes": hashes,
        "initial_source_hashes": before,
        "source_changes_during_validation": changed,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("rdkit", "rdchiral", "syntheseus", "pydantic", "fastapi", "pytest")
        },
    }
    (destination / "validation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="ascii"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
