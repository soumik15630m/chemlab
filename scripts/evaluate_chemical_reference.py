"""Freeze a new evidence policy before scoring the untouched expert reference split."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from chemlab.evaluation.chemical_reference import prepare_reference, score_reference
from chemlab.evidence.chemical_checks import POLICY
from chemlab.evidence.chemical_service import KnowledgeConfig, assess_batch, register_knowledge
from chemlab.evidence.reaction_library import file_digest
from chemlab.records import canonical_bytes, digest
from chemlab.store import IntegrityError, Store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("knowledge", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("var/reaction-data/downloads/URSA-reaction-plausibility-bench-2026.csv"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.exists():
        raise FileExistsError("Evaluations are immutable; choose a new run directory")
    protocol = json.loads((root / "configs/chemical-evaluation/protocol.json").read_bytes())
    prepared = prepare_reference(args.reference.read_bytes(), protocol)
    config = KnowledgeConfig.model_validate_json(args.knowledge.read_bytes())
    if not (config.source_path and config.context_path and config.mapper_command):
        raise ValueError("This evaluation requires all declared knowledge and mapping components")
    args.output.mkdir(parents=True)
    store = Store(args.output / "evidence")
    knowledge_ref = register_knowledge(store, "frozen-evaluation-knowledge", config)
    files = [
        "chemlab/chemistry/identity.py",
        "chemlab/chemistry/__init__.py",
        "chemlab/records.py",
        "chemlab/store.py",
        "chemlab/registry.py",
        "chemlab/evidence/bounded.py",
        "chemlab/evidence/chemical_checks.py",
        "chemlab/evidence/chemical_service.py",
        "chemlab/evidence/reaction_library.py",
        "chemlab/evidence/reaction_templates.py",
        "chemlab/evidence/mapping_worker.py",
        "chemlab/evidence/reaction_diagnostics.py",
        "chemlab/evaluation/chemical_reference.py",
        "scripts/evaluate_chemical_reference.py",
        "requirements.lock",
        "requirements-mapping.lock",
    ]
    hashes = {name: file_digest(root / name) for name in files}
    frozen = {
        "policy": POLICY,
        "policy_hash": digest(POLICY),
        "protocol": protocol,
        "protocol_hash": prepared["protocol_hash"],
        "knowledge_ref": knowledge_ref,
        "source_sha256": prepared["source_sha256"],
        "implementation_hashes": hashes,
    }
    freeze_path = args.output / "frozen-policy.json"
    with freeze_path.open("xb") as stream:
        stream.write(canonical_bytes(frozen))
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                "stage": "policy_frozen",
                "freeze_sha256": file_digest(freeze_path),
                "reference_rows": prepared["input_rows"],
            }
        ),
        flush=True,
    )
    excluded = frozenset(
        key for key, query in prepared["inputs"].items() if query["partition"] == "final_reference"
    )
    # The checker sees only molecular inputs. Human labels and scorer fields stay here.
    result = assess_batch(
        store,
        [
            {"product": q["product"], "precursors": q["precursors"]}
            for q in prepared["inputs"].values()
        ],
        config,
        excluded=excluded,
    )
    if any(file_digest(root / name) != expected for name, expected in hashes.items()):
        raise IntegrityError("Frozen implementation changed during reference evaluation")
    report = score_reference(prepared, result["results"], digest(POLICY))
    result_ref = store.put("chemical_reference_outputs", result)
    report.update(
        {
            "result_ref": result_ref,
            "knowledge_ref": knowledge_ref,
            "frozen_policy_sha256": file_digest(freeze_path),
        }
    )
    (args.output / "metrics.json").write_bytes(canonical_bytes(report))
    (args.output / "references.json").write_bytes(canonical_bytes(prepared))
    marker = args.output / "complete.json.partial"
    with marker.open("xb") as stream:
        stream.write(
            canonical_bytes(
                {
                    "metrics_sha256": file_digest(args.output / "metrics.json"),
                    "frozen_policy_sha256": file_digest(freeze_path),
                    "references_sha256": file_digest(args.output / "references.json"),
                }
            )
        )
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(marker, args.output / "complete.json")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
