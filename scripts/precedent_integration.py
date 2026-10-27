from __future__ import annotations

import json
import sys
from pathlib import Path

from chemlab.application import Application
from chemlab.records import RunConfig
from chemlab.registry import Registry
from chemlab.store import Store


def main(output: Path) -> int:
    store = Store("var")
    registry = Registry(store)
    config = RunConfig(
        backward_manifest=registry.resolve("generator-v1", "model_manifest"),
        forward_manifest=registry.resolve("checker-v1", "model_manifest"),
        stock_ref=registry.resolve("paroutes-n1-v2", "stock"),
        corpus_ref=registry.resolve("uspto50k-training-v1", "corpus"),
        prediction_count=10,
        forward_k=5,
        logical_expansion_limit=4,
        route_limit=2,
        max_depth=4,
        seed=0,
    )
    app = Application(store)
    run_id = app.prepare("Oc1ccc(OCc2ccccc2)c(Br)c1", config)
    print(f"Public precedent integration run: {run_id}", flush=True)
    app.execute(run_id)
    row = app.run(run_id)
    result = {
        "run_id": run_id,
        "state": row["state"],
        "error": row["error"],
        "scope": (
            "Integration with public training corpus; overlap not audited; "
            "no chemical accuracy claim"
        ),
    }
    if row["state"] == "complete":
        bundle = row["result"]
        reports = [
            value["payload"]
            for value in bundle["objects"].values()
            if value["kind"] == "verification_report"
        ]
        result["precedent"] = [
            value
            for report in reports
            for value in report["precedent"].values()
            if isinstance(value, dict)
        ]
        result["groups"] = {name: len(items) for name, items in bundle["groups"].items()}
        result["config_ref"] = row["config_ref"]
        result["source_artifacts_in_bundle"] = sum(
            value["kind"] == "source_csv" for value in bundle["objects"].values()
        )
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="ascii")
    ok = (
        row["state"] == "complete"
        and result.get("source_artifacts_in_bundle") == 1
        and all(item["status"] == "pass" for item in result.get("precedent", []))
    )
    print(json.dumps({"run_id": run_id, "passed": ok, "state": row["state"]}), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
