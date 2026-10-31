"""Compare the isolated mapping adapter to direct pinned upstream inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from chemlab.evidence.chemical_checks import validate_mapping
from chemlab.evidence.mapping_worker import map_requests
from chemlab.evidence.reaction_library import reaction_input
from chemlab.records import canonical_bytes


def main() -> None:
    import numpy as np
    import rxnmapper
    import torch
    from rxnmapper import RXNMapper

    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Parity results are immutable")
    manifest = json.loads(Path("configs/mapping/rxnmapper.json").read_bytes())
    queries = [
        reaction_input(product, precursors)
        for product, precursors in (
            ("CC=O", ("CCO",)),
            ("CC(=O)NC", ("CN", "CC(=O)Cl")),
            ("C[C@H](O)F", ("C[C@H](O)F",)),
        )
    ]
    adapted = map_requests(queries, manifest)
    torch.manual_seed(0)
    np.random.seed(0)
    model = Path(rxnmapper.__file__).parent / "models/transformers/albert_heads_8_uspto_all_1310k"
    direct = RXNMapper(config={"model_path": str(model)})
    direct.model.to(device="cpu", dtype=torch.float32)
    direct.model.eval()
    cases = []
    for query, output in zip(queries, adapted["results"], strict=True):
        raw = direct.get_attention_guided_atom_maps(
            [
                ".".join(query["precursors"]) + ">>" + query["product"],
            ]
        )[0]
        assert output["raw_output"] == [raw]
        cases.append(
            {
                "input": query,
                "raw_parity": raw == output["raw_prediction"],
                "validation": validate_mapping(query, output),
            }
        )
    oversize = map_requests([reaction_input("CO", ("C" * 600,))], manifest)
    bounded = oversize["results"][0]["status"] == "error" and "truncation forbidden" in (
        oversize["results"][0].get("error", "")
    )
    malformed_raw = [{"mapped_rxn": "", "confidence": 0.5, "provider_extra": "retained"}]
    with patch.object(RXNMapper, "get_attention_guided_atom_maps", return_value=malformed_raw):
        malformed = map_requests(queries[:1], manifest)["results"][0]
    preserved_error = malformed["status"] == "error" and malformed["raw_output"] == malformed_raw
    passed = preserved_error and (
        all(case["raw_parity"] and case["validation"]["status"] == "pass" for case in cases)
        and bounded
    )
    result = {
        "passed": passed,
        "cases": cases,
        "oversize_input_fails_without_truncation": bounded,
        "malformed_raw_output_retained_on_error": preserved_error,
        "provider_ref": adapted["provider_ref"],
        "runtime": adapted["runtime"],
        "scope": "Pinned upstream/adapter parity and representation; not chemical feasibility",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
