import json
import os
import subprocess
import sys
import textwrap


def test_budgeted_search_is_stable_across_hash_seeds():
    program = textwrap.dedent("""
        import json, tempfile
        from pathlib import Path
        from chemlab.adapters.models import ModelService
        from chemlab.evidence.checks import import_stock, load_stock
        from chemlab.planning import search
        from chemlab.records import ModelManifest, RunConfig, digest
        from chemlab.store import Store
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            data = {"CCCCC": [{"precursors": ["CCC", "CC"], "score": 0.8}],
                    "CC": [{"precursors": ["C"], "score": 0.8}],
                    "CCC": [{"precursors": ["CO"], "score": 0.8}]}
            file = path / "predictions.json"
            file.write_text(json.dumps(data))
            store = Store(path / "store")
            manifest = ModelManifest(name="synthetic", kind="template_free", backend="replay",
                checkpoint=str(file), checkpoint_hash=digest(data), training_provenance="fixture",
                license="fixture", score_semantics="probability", score_direction="higher",
                replay_file=str(file))
            ref = store.put("model_manifest", manifest)
            stock_ref = import_stock(store, ["C", "CO"], "fixture", "fixture", "fixture")
            config = RunConfig(backward_manifest=ref, forward_manifest=None, stock_ref=stock_ref,
                prediction_count=10, forward_k=5, logical_expansion_limit=2, route_limit=10,
                max_depth=5, seed=0)
            result = search("CCCCC", config, ModelService(store, ref), load_stock(store, stock_ref))
            with store.connect() as conn:
                query = "SELECT ref FROM artifacts WHERE kind='prediction' ORDER BY rowid"
                refs = [r[0] for r in conn.execute(query)]
            print(json.dumps({"inputs": [store.get(r)["effective_input"] for r in refs],
                "expansions": result.logical_expansions, "termination": result.termination_reason,
                "routes": result.candidate_routes_found}, sort_keys=True))
    """)
    observations = []
    for seed in ("1", "2", "17"):
        result = subprocess.run(
            [sys.executable, "-c", program],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        observations.append(json.loads(result.stdout))
    assert (
        observations
        == [
            {
                "inputs": ["CCCCC", "CC"],
                "expansions": 2,
                "termination": "budget_exhausted",
                "routes": 0,
            }
        ]
        * 3
    )
