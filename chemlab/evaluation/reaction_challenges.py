"""Evaluate development observations without treating user labels as engine evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any

from chemlab.evidence.reaction_diagnostics import _payload, diagnose_route
from chemlab.records import digest
from chemlab.store import IntegrityError


def evaluate_challenges(snapshot: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("scope") != "development_challenge_snapshot"
    ):
        raise ValueError("Unsupported challenge snapshot")
    if labels.get("schema_version") != 1 or labels.get("partition") != "development":
        raise ValueError("Challenge labels must remain development data")
    reports = snapshot["reports"]
    objects = snapshot["objects"]
    run_ids = [source["completion"]["run_id"] for source in reports]
    if len(set(run_ids)) != len(run_ids) or set(run_ids) != set(labels["reports"]):
        raise ValueError("Label reports differ from challenge source reports")
    for ref, envelope in objects.items():
        if digest(envelope) != ref:
            raise IntegrityError("Challenge object hash mismatch")
    rows = []
    for source in reports:
        completion = source["completion"]
        if completion.get("state") != "complete":
            raise IntegrityError("Challenge source was not a completed bundle")
        for name, ref in completion["files"].items():
            if name != f"objects/{ref}.json":
                raise IntegrityError("Challenge source has invalid object paths")
        run = _payload(objects, completion["run_ref"], "run_manifest")
        items = [item for group in completion["groups"].values() for item in group]
        expected_numbers = {str(n) for n in range(1, len(items) + 1)}
        run_labels = labels["reports"][completion["run_id"]]
        if set(run_labels) != expected_numbers:
            raise ValueError("Every PDF route needs an explicit label or unlabelled marker")
        selected = {completion["run_ref"]}
        for number, item in enumerate(items, 1):
            selected.update(item.values())
            result = diagnose_route({**completion, "objects": objects}, item["route_ref"])
            if result["target"] != run["target"]:
                raise IntegrityError("Challenge report target differs from source run")
            label = run_labels[str(number)]
            if label not in ("correct", "incorrect", "unlabelled"):
                raise ValueError("Unsupported user label")
            for step in result["steps"]:
                selected.add(step["prediction_ref"])
                selected.update(step["forward_refs"])
            rows.append(
                {
                    "run_id": completion["run_id"],
                    "pdf_route_number": number,
                    "pdf_sha256": source["pdf_sha256"],
                    "user_route_label": label,
                    "step_labels": "not_supplied",
                    "observations": result,
                }
            )
        if not selected.issubset(set(completion["files"].values())):
            raise IntegrityError("Selected challenge evidence was not in the source manifest")
    counts = Counter(row["user_route_label"] for row in rows)
    conflicts = Counter(
        f"{row['user_route_label']}/{row['observations']['recorded_forward_status']}"
        for row in rows
    )
    return {
        "scope": "Development observations; not a final evaluation or chemical classifier",
        "snapshot_hash": digest(snapshot),
        "labels_hash": digest(labels),
        "label_source": labels["label_source"],
        "partition": "development",
        "route_counts": dict(sorted(counts.items())),
        "step_occurrences": sum(len(row["observations"]["steps"]) for row in rows),
        "forward_status_by_user_label": dict(sorted(conflicts.items())),
        "routes": rows,
    }
