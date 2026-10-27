"""Real-model integration smoke test; not a chemical feasibility benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from chemlab.application import Application
from chemlab.chemistry import require_molecule
from chemlab.evidence.checks import load_stock
from chemlab.records import RunConfig
from chemlab.registry import Registry
from chemlab.store import Store


def main(output: Path):
    store = Store("var")
    registry = Registry(store)
    stock_ref = registry.resolve("paroutes-n1-v2", "stock")
    stock = load_stock(store, stock_ref)
    candidates = ["Oc1ccc(OCc2ccccc2)c(Br)c1", "COc1ccc(CCNC(=O)c2ccccc2)cc1"]
    target = next(
        smiles
        for smiles in candidates
        if require_molecule(smiles).canonical_smiles not in stock.identities
    )
    config = RunConfig(
        backward_manifest=registry.resolve("generator-v1", "model_manifest"),
        forward_manifest=registry.resolve("checker-v1", "model_manifest"),
        stock_ref=stock_ref,
        prediction_count=10,
        forward_k=5,
        logical_expansion_limit=4,
        route_limit=2,
        max_depth=4,
        seed=0,
    )
    app = Application(store)
    run_id = app.prepare(target, config)
    print(f"Real inference smoke run: {run_id}, target: {target}", flush=True)
    app.execute(run_id)
    row = app.run(run_id)
    result = {
        "run_id": run_id,
        "state": row["state"],
        "error": row["error"],
        "scope": "Real-model pipeline integration only; not a chemical feasibility benchmark",
        "config": config.model_dump(mode="json"),
    }
    if row["state"] == "complete":
        bundle = row["result"]
        manifest = bundle["objects"][bundle["run_ref"]]["payload"]
        result.update(
            {
                "termination": manifest["search"]["termination_reason"],
                "candidate_routes_found": manifest["search"]["candidate_routes_found"],
                "logical_expansions": manifest["search"]["logical_expansions"],
                "actual_inferences": manifest["search"]["actual_inferences"],
                "search_error": manifest["search"]["error"],
                "groups": {key: len(items) for key, items in bundle["groups"].items()},
                "software": manifest["software"],
            }
        )
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="ascii")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if row["state"] == "complete" and not result.get("search_error") else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
