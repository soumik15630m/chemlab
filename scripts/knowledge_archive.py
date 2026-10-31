"""Export or restore complete hash-pinned reaction knowledge without replacing data."""

import argparse
import json
from pathlib import Path

from chemlab.evidence.knowledge_distribution import export_knowledge, restore_knowledge
from chemlab.evidence.reaction_library import ReactionLibrary
from chemlab.evidence.reaction_templates import ContextLibrary

parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest="command", required=True)
export = commands.add_parser("export")
export.add_argument("source", type=Path)
export.add_argument("source_hash")
export.add_argument("contexts", type=Path)
export.add_argument("context_hash")
export.add_argument("output", type=Path)
restore = commands.add_parser("restore")
restore.add_argument("archive", type=Path)
restore.add_argument("archive_hash")
restore.add_argument("destination", type=Path)
args = parser.parse_args()
if args.command == "export":
    source = ReactionLibrary(args.source, args.source_hash)
    contexts = ContextLibrary(args.contexts, args.context_hash, source)
    result = export_knowledge(source, contexts, args.output)
else:
    result = restore_knowledge(args.archive, args.archive_hash, args.destination)
print(json.dumps(result), flush=True)
