"""Copy a complete pinned reaction index without changing its bytes or references."""

import argparse
from pathlib import Path

from chemlab.evidence.reaction_library import materialize_snapshot

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("manifest_hash")
parser.add_argument("destination", type=Path)
parser.add_argument("--database", choices=("reactions.sqlite3", "contexts.sqlite3"), required=True)
args = parser.parse_args()
materialize_snapshot(args.source, args.manifest_hash, args.destination, args.database)
print("Pinned index copied and verified; original snapshot retained", flush=True)
