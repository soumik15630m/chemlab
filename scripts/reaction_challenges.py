"""Replay the user-labelled development cases without loading neural models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chemlab.evaluation.reaction_challenges import evaluate_challenges
from chemlab.records import canonical_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/reaction-challenges"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads((args.fixtures / "snapshot.json").read_text(encoding="ascii"))
    labels = json.loads((args.fixtures / "labels.json").read_text(encoding="ascii"))
    report = evaluate_challenges(snapshot, labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(canonical_bytes(report))
    print(
        json.dumps({key: value for key, value in report.items() if key != "routes"}, sort_keys=True)
    )


if __name__ == "__main__":
    main()
