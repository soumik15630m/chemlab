"""Validate fresh native startup or an initialized Compose service, inside Docker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


def request(url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    with urlopen(
        Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=60
    ) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    process = None
    report = {"passed": False, "mode": "native" if args.native else "compose"}
    log = (args.output / f"{report['mode']}-startup.log").open("w", encoding="utf-8")
    try:
        if args.native:
            assert args.url == "http://127.0.0.1:8091"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "start_venv.py",
                    "--venv",
                    "/tmp/chemlab-native",
                    "--state",
                    "/tmp/chemlab-native-state",
                    "--port",
                    "8091",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.monotonic() + 1800
        while True:
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"Native launcher exited {process.returncode}; see startup log")
            try:
                health = request(args.url + "/api/health")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("Startup did not reach HTTP readiness") from None
                time.sleep(2)
        assert health == {"status": "ok", "planner": "Syntheseus Retro*", "identity": "identity-v1"}
        registry = request(args.url + "/api/registry")
        refs = {row["alias"]: row["ref"] for row in registry}
        assert set(refs) == {"generator-v1", "checker-v1", "paroutes-n1-v2", "uspto50k-training-v1"}
        corpus = next(row["record"] for row in registry if row["kind"] == "corpus")
        assert corpus["count"] == 40008
        with urlopen(args.url + "/api/molecule.svg?smiles=CCO", timeout=20) as response:
            assert b"<svg" in response.read()
        report.update(
            health=health, registry=refs, corpus_records=corpus["count"], svg_rendered=True
        )
        if args.native:
            environment = json.loads(
                subprocess.check_output(
                    [
                        "/tmp/chemlab-native/bin/python",
                        "-c",
                        "import sys,json,importlib.metadata as m; "
                        "print(json.dumps({'isolated':sys.prefix!=sys.base_prefix,"
                        "'torch':m.version('torch'),'rdkit':m.version('rdkit')}))",
                    ],
                    text=True,
                )
            )
            assert environment == {"isolated": True, "torch": "2.14.1+cpu", "rdkit": "2026.9.1"}
            config = {
                "backward_manifest": refs["generator-v1"],
                "forward_manifest": refs["checker-v1"],
                "stock_ref": refs["paroutes-n1-v2"],
                "corpus_ref": refs["uspto50k-training-v1"],
                "prediction_count": 10,
                "forward_k": 5,
                "logical_expansion_limit": 4,
                "route_limit": 2,
                "max_depth": 4,
                "seed": 0,
            }
            run = request(
                args.url + "/api/runs", {"target": "Oc1ccc(OCc2ccccc2)c(Br)c1", "config": config}
            )
            deadline = time.monotonic() + 600
            while True:
                row = request(args.url + "/api/runs/" + run["id"])
                if row["state"] in ("complete", "error"):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("Native real-model route did not complete")
                time.sleep(2)
            assert row["state"] == "complete", row["error"]
            groups = {key: len(value) for key, value in row["result"]["groups"].items()}
            assert groups["verified_consistent"] == 2
            report.update(environment=environment, route_groups=groups, run_id=run["id"])
        report["passed"] = True
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=20)
        log.close()
        (args.output / f"{report['mode']}-startup.json").write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="ascii",
        )
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
