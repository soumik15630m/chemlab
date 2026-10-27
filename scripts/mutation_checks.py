"""Seed isolated behavioral defects; require assertion failures, not setup errors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

MUTATIONS = [
    (
        "M14-compose-initialization-gate",
        "compose.yaml",
        "service_completed_successfully",
        "service_started",
        "tests/test_bootstrap.py::test_compose_initialization_gate_and_persistent_mounts",
    ),
    (
        "M13-bootstrap-failure-propagation",
        "chemlab/bootstrap.py",
        "cwd=root,\n        env=env,\n        check=True,",
        "cwd=root,\n        env=env,\n        check=False,",
        "tests/test_bootstrap.py::test_download_failure_blocks_registration",
    ),
    (
        "M11-venv-isolation",
        "chemlab/bootstrap.py",
        "python = virtual_python(directory, sys.platform)",
        "python = Path(sys.executable)",
        "tests/test_bootstrap.py::test_native_installs_and_runs_only_selected_virtual_interpreter",
    ),
    (
        "M12-setup-only-no-server",
        "chemlab/bootstrap.py",
        "if args.prepare_only:\n        return 0",
        "if False:\n        return 0",
        "tests/test_bootstrap.py::test_prepare_only_has_no_server_side_effect",
    ),
    (
        "M10-public-source-integrity",
        "chemlab/evidence/ingestion.py",
        "if actual != expected:",
        "if False:",
        "tests/test_ingestion.py::test_source_blob_mismatch_is_rejected",
    ),
    (
        "M09-tokenizer-admission",
        "chemlab/adapters/sdk.py",
        "if any(token not in tokenizer.vocab_dict for token in tokens):",
        "if False:",
        "tests/test_plugins.py::test_tokenizer_cannot_silently_lose_input_information",
    ),
    (
        "M01-stereo-preservation",
        "chemlab/chemistry/identity.py",
        "isomericSmiles=True",
        "isomericSmiles=False",
        "tests/test_identity.py::test_identity_contract",
    ),
    (
        "M02-ancestor-recurrence",
        "chemlab/verification/verifier.py",
        "mid in reached or identities[mid] in ancestors",
        "mid in reached",
        "tests/test_verification.py::test_molecular_cycle_with_fresh_occurrences",
    ),
    (
        "M03-precursor-completeness",
        "chemlab/verification/verifier.py",
        "if exported != authoritative:",
        "if False:",
        "tests/test_verification.py::test_export_corruptions_are_rejected[drop_precursor]",
    ),
    (
        "M04-score-direction",
        "chemlab/adapters/models.py",
        "(candidate.cost, candidate.index) < (",
        "(candidate.cost, candidate.index) > (",
        "tests/test_adapters.py::test_lower_cost_duplicate_wins",
    ),
    (
        "M05-fail-precedence",
        "chemlab/verification/verifier.py",
        'if any(c.status == "fail" for c in mandatory):',
        "if False:",
        "tests/test_verification.py::test_fail_dominates_unknown",
    ),
    (
        "M06-cache-integrity",
        "chemlab/store.py",
        "if hashlib.sha256(data).hexdigest() != ref:",
        "if False:",
        "tests/test_infrastructure.py::test_corrupt_artifact_is_never_a_cache_hit",
    ),
    (
        "M07-expansion-accounting",
        "chemlab/adapters/models.py",
        "self.logical_expansions += len(inputs)",
        "self.logical_expansions += 0",
        "tests/test_adapters.py::test_cache_preserves_logical_attempts",
    ),
    (
        "M08-report-binding",
        "chemlab/reporting/bundles.py",
        "if report.route_hash != digest(route):",
        "if False:",
        "tests/test_infrastructure.py::test_report_for_another_route_cannot_publish",
    ),
]


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    baseline = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--basetemp=/tmp/mutation-baseline",
            "-o",
            "cache_dir=/tmp/mutation-cache",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if baseline.returncode:
        raise RuntimeError("Mutation baseline failed:\n" + baseline.stdout + baseline.stderr)
    results = []
    for name, filename, old, new, test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="chemlab-mutant-") as temp:
            directory = Path(temp)
            shutil.copyfile(root / "compose.yaml", directory / "compose.yaml")
            shutil.copytree(
                root / "chemlab",
                directory / "chemlab",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            shutil.copytree(
                root / "tests", directory / "tests", ignore=shutil.ignore_patterns("__pycache__")
            )
            path = directory / filename
            original = path.read_text(encoding="utf-8")
            if old not in original:
                raise RuntimeError(f"Mutation anchor missing: {name}")
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(directory), "PYTHONDONTWRITEBYTECODE": "1"}
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test,
                    "-q",
                    "--basetemp",
                    str(directory / "tmp"),
                    "--junitxml",
                    str(directory / "result.xml"),
                    "-o",
                    "cache_dir=/tmp/mutation-cache",
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            suite = ET.parse(directory / "result.xml").getroot()
            failures = sum(int(s.get("failures", 0)) for s in suite.iter("testsuite"))
            errors = sum(int(s.get("errors", 0)) for s in suite.iter("testsuite"))
            detected = output.returncode == 1 and failures > 0 and errors == 0
            results.append(
                {
                    "name": name,
                    "test": test,
                    "detected": detected,
                    "assertion_failures": failures,
                    "setup_errors": errors,
                }
            )
            print(f"{name}: {'detected' if detected else 'SURVIVED OR INVALID'}", flush=True)
    return {
        "baseline_passed": True,
        "mutants": results,
        "passed": all(r["detected"] for r in results),
        "scope": "Fourteen named behavioral mutants; no claim of exhaustive mutation coverage",
    }


if __name__ == "__main__":
    report = run()
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mutation-report.json")
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    raise SystemExit(0 if report["passed"] else 1)
