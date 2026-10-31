"""Replay all original challenge reactions without turning route labels into step truth."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from chemlab.evidence.chemical_service import KnowledgeConfig, assess_batch
from chemlab.evidence.reaction_diagnostics import diagnose_route
from chemlab.evidence.reaction_library import file_digest, index_reaction_inputs, reaction_input
from chemlab.records import canonical_bytes, digest
from chemlab.store import Store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("knowledge", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Challenge replays never overwrite reports")
    snapshot_path = Path("tests/fixtures/reaction-challenges/snapshot.json")
    labels_path = Path("tests/fixtures/reaction-challenges/labels.json")
    snapshot = json.loads(snapshot_path.read_bytes())
    labels = json.loads(labels_path.read_bytes())
    queries, routes = [], []
    for source in snapshot["reports"]:
        bundle = {**source["completion"], "objects": snapshot["objects"]}
        number = 0
        for group in bundle["groups"].values():
            for item in group:
                number += 1
                observations = diagnose_route(bundle, item["route_ref"])
                steps = []
                for step in observations["steps"]:
                    query = reaction_input(step["product"], tuple(step["precursors"]))
                    queries.append(query)
                    steps.append(
                        {
                            "step_id": step["step_id"],
                            "input_key": digest(query),
                            "prediction_ref": step["prediction_ref"],
                            "candidate_index": step["candidate_index"],
                        }
                    )
                routes.append(
                    {
                        "run_id": bundle["run_id"],
                        "route_ref": item["route_ref"],
                        "pdf_route_number": number,
                        "steps": steps,
                        "user_route_label": labels["reports"][bundle["run_id"]][str(number)],
                        "step_labels": "not_supplied",
                    }
                )
    args.output.mkdir(parents=True)
    store = Store(args.output / "evidence")
    config = KnowledgeConfig.model_validate_json(args.knowledge.read_bytes())
    # Only molecular inputs cross the checker boundary; route labels remain above it.
    unique = index_reaction_inputs(queries)
    result = assess_batch(store, list(unique.values()), config)
    ref = store.put("user_chemical_challenge_outputs", result)
    counts = Counter(r["evidence_outcome"] for r in result["results"].values())
    for route in routes:
        route["step_findings"] = dict(
            Counter(
                result["results"][step["input_key"]]["evidence_outcome"] for step in route["steps"]
            )
        )
    report = {
        "scope": "Development replay; route labels are not step-level chemical truth",
        "snapshot_sha256": file_digest(snapshot_path),
        "labels_sha256": file_digest(labels_path),
        "unique_reactions": len(unique),
        "step_occurrences": sum(len(r["steps"]) for r in routes),
        "counts": dict(counts),
        "result_ref": ref,
        "routes": routes,
        "policy_hash": result["policy_hash"],
        "chemical_feasibility": "unresolved",
    }
    (args.output / "report.json").write_bytes(canonical_bytes(report))
    (args.output / "complete.json").write_bytes(
        canonical_bytes(
            {
                "report_sha256": file_digest(args.output / "report.json"),
                "result_ref": ref,
            }
        )
    )
    print(json.dumps({"unique_reactions": len(unique), "counts": dict(counts)}), flush=True)


if __name__ == "__main__":
    main()
