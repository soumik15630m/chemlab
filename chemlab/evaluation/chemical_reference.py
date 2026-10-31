"""Separate human reference labels from checker inputs and evidence indexes."""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from typing import Any

from rdkit import Chem

from chemlab.evidence.reaction_library import reaction_input
from chemlab.records import digest
from chemlab.store import IntegrityError


def prepare_reference(raw: bytes, protocol: dict[str, Any]) -> dict[str, Any]:
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if len(raw) != protocol["bytes"] or blob != protocol["git_blob"]:
        raise IntegrityError("Reference bytes differ from the frozen source")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if not {"reaction_smiles", "expert_score"}.issubset(reader.fieldnames or []):
        raise ValueError("Missing benchmark input or human reference column")
    inputs: dict[str, dict[str, Any]] = {}
    references: dict[str, list[dict]] = defaultdict(list)
    counts: Counter = Counter()
    errors = []
    for number, row in enumerate(reader, 1):
        label = row["expert_score"]
        if label not in ("0", "1"):
            raise ValueError("Unsupported expert reference label")
        counts[label] += 1
        try:
            left, agents, right = row["reaction_smiles"].split(">")
            if agents:
                raise ValueError("Unexpected agent field in a condition-free reference")
            query = reaction_input(right, tuple(left.split(".")))
            key = digest(query)
            if key in inputs and any(inputs[key][name] != query[name] for name in query):
                raise IntegrityError("Different full reference identities have the same index hash")
            grouping = Chem.MolToSmiles(
                Chem.MolFromSmiles(query["product"]),
                canonical=True,
                isomericSmiles=False,
            )
            bucket = (
                int(
                    hashlib.sha256(
                        ("ChemLab-chemical-reference-2026-10-31:" + grouping).encode("utf-8")
                    ).hexdigest(),
                    16,
                )
                % 5
            )
            partition = "final_reference" if bucket == 4 else "development"
            inputs[key] = {"key": key, **query, "partition": partition, "group": grouping}
            references[key].append({"row": number, "expert_label": int(label)})
        except IntegrityError:
            raise
        except Exception as exc:
            errors.append({"row": number, "error": str(exc), "expert_label": int(label)})
    if (
        sum(counts.values()) != protocol["expected_rows"]
        or dict(counts) != protocol["expected_label_counts"]
    ):
        raise IntegrityError("Reference counts differ from the frozen protocol")
    return {
        "protocol_hash": digest(protocol),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "input_rows": sum(counts.values()),
        "inputs": inputs,
        "references": dict(references),
        "errors": errors,
    }


def score_reference(prepared: dict, results: dict[str, dict], policy_hash: str) -> dict:
    if set(results) != set(prepared["inputs"]):
        raise ValueError("Every supported unique reference input needs a checker result")
    metrics: dict[str, Counter] = defaultdict(Counter)
    for error in prepared["errors"]:
        metrics["input_errors"][str(error["expert_label"])] += 1
    for key, query in prepared["inputs"].items():
        labels = {entry["expert_label"] for entry in prepared["references"][key]}
        partition = query["partition"]
        metrics[partition]["unique_inputs"] += 1
        metrics[partition]["raw_rows"] += len(prepared["references"][key])
        if len(labels) != 1:
            metrics[partition]["reference_conflicts"] += 1
            continue
        label = next(iter(labels))
        metrics[partition][f"expert_{label}/inputs"] += 1
        result = results[key]
        if result.get("input_key") != key or result.get("policy_hash") != policy_hash:
            raise IntegrityError("Reference result input or frozen policy binding differs")
        # These outcomes concern evidence obligations, never experimental truth.
        state = result["evidence_outcome"]
        if state not in ("support", "contradiction", "unresolved", "error"):
            raise ValueError("Unsupported reaction evidence outcome")
        metrics[partition][f"expert_{label}/{state}"] += 1
        for name, supported in (
            ("exact_precedent", "reported_match"),
            ("context_precedent", "context_replay_match"),
        ):
            if result["checks"][name]["status"] == supported:
                metrics[partition][f"expert_{label}/{name}_coverage"] += 1
    return {
        "protocol_hash": prepared["protocol_hash"],
        "policy_hash": policy_hash,
        "source_sha256": prepared["source_sha256"],
        "all_reference_rows": prepared["input_rows"],
        "metrics": {key: dict(value) for key, value in sorted(metrics.items())},
        "limitation": (
            "Expert-labelled proposals, not experimental success/failure. "
            "Evidence support and represented-input contradictions do not certify feasibility."
        ),
    }
