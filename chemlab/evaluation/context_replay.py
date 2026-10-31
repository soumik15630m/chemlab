"""Unpromoted context-replay experiment; no imports from the runtime engine."""

import json
from functools import lru_cache

from chemlab.evidence.reaction_templates import _extract_context as extract_context
from chemlab.records import canonical_bytes


class IncompleteContext(Exception):
    def __init__(self, result: dict):
        self.result = result


@lru_cache(maxsize=32768)
def observed_context(mapped: str, product: str, precursors: tuple[str, ...]) -> bytes:
    result = extract_context(mapped, product, precursors)
    if result["status"] != "observed":
        raise IncompleteContext(result)
    return canonical_bytes(result)


def replay_context(mapped: str, product: str, precursors: tuple[str, ...]) -> dict:
    try:
        return json.loads(observed_context(mapped, product, precursors))
    except IncompleteContext as exc:
        return exc.result
