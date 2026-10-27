from __future__ import annotations

import json
import sys
from pathlib import Path

from chemlab.registry import Registry, parity
from chemlab.store import Store


def main(path: Path) -> int:
    store = Store("var")
    registry = Registry(store)
    reports = []
    for alias, inputs in [("generator-v1", ["CCOC(C)=O"]), ("checker-v1", ["CC(=O)O.CCO"])]:
        report = parity(store, registry.resolve(alias, "model_manifest"), inputs, 5)
        reports.append({"alias": alias, **report})
        print(f"{alias}: {'passed' if report['passed'] else 'FAILED'}", flush=True)
    result = {
        "reports": reports,
        "passed": all(report["passed"] for report in reports),
        "scope": "Direct/provider-boundary parity for one input per pretrained model",
    }
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="ascii")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
