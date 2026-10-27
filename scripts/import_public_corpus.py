from __future__ import annotations

import json
import sys
from pathlib import Path

from chemlab.evidence.ingestion import register_public_training
from chemlab.store import Store


def main(output: Path):
    root = Path("models")
    raw = (root / "openretro-train.csv").read_bytes()
    metadata = json.loads((root / "openretro-train-source.json").read_text(encoding="utf-8"))
    store = Store("var")
    report = register_public_training(store, raw, metadata)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
