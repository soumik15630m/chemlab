"""Export or restore a frozen runtime snapshot; never overwrite existing state."""

import argparse
import json
from pathlib import Path

from chemlab.distribution import export_runtime, restore_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    action = export_runtime if args.action == "export" else restore_runtime
    print(json.dumps(action(args.source, args.destination), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
