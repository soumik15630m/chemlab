from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from chemlab.chemistry import require_molecule
from chemlab.records import Record, digest


class ReactionExample(Record):
    source_id: str
    product: str
    precursors: tuple[str, ...]
    partition: Literal["training", "development", "final_reference"]
    mapped_reaction: str | None = None
    reference: str | None = None


def reaction_identity(example: ReactionExample) -> str:
    return digest(
        {
            "product": require_molecule(example.product).canonical_smiles,
            "precursors": sorted(require_molecule(s).canonical_smiles for s in example.precursors),
        }
    )


def read_examples(path: Path) -> list[ReactionExample]:
    examples = [
        ReactionExample.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({e.source_id for e in examples}) != len(examples):
        raise ValueError("Dataset source IDs must be unique")
    for example in examples:
        require_molecule(example.product)
        if not example.precursors:
            raise ValueError("Reaction example requires precursors")
        for smiles in example.precursors:
            require_molecule(smiles)
    return examples


def audit(examples: list[ReactionExample]) -> dict:
    partitions = {
        name: [e for e in examples if e.partition == name]
        for name in ("training", "development", "final_reference")
    }
    counts = dict(Counter(e.partition for e in examples))
    overlap = {}
    for left, right in [
        ("training", "development"),
        ("training", "final_reference"),
        ("development", "final_reference"),
    ]:
        reactions = {reaction_identity(e) for e in partitions[left]} & {
            reaction_identity(e) for e in partitions[right]
        }
        targets = {require_molecule(e.product).canonical_smiles for e in partitions[left]} & {
            require_molecule(e.product).canonical_smiles for e in partitions[right]
        }
        overlap[f"{left}:{right}"] = {
            "reaction_overlap": len(reactions),
            "target_overlap": len(targets),
        }
    return {"counts": counts, "overlap": overlap, "template_overlap": "unknown_not_supplied"}


def export_training(examples: list[ReactionExample], output: Path) -> dict:
    report = audit(examples)
    for pair in ("training:final_reference", "development:final_reference"):
        if report["overlap"][pair]["reaction_overlap"]:
            raise ValueError("Training/development reactions overlap final-reference records")
    if output.exists():
        raise FileExistsError("Dataset exports are immutable; choose a new output directory")
    output.mkdir(parents=True)
    for name in ("training", "development"):
        selected = sorted((e for e in examples if e.partition == name), key=lambda e: e.source_id)
        with (output / f"{name}.jsonl").open("w", encoding="ascii") as stream:
            for example in selected:
                record = {
                    "source_id": example.source_id,
                    "product": require_molecule(example.product).canonical_smiles,
                    "precursors": [
                        require_molecule(s).canonical_smiles for s in example.precursors
                    ],
                    "original": example.model_dump(mode="json"),
                }
                stream.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
    (output / "audit.json").write_text(
        json.dumps(report, sort_keys=True, indent=2), encoding="ascii"
    )
    return report
