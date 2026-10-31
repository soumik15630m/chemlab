"""Isolated RXNMapper JSON worker; raw predictions precede interpretation."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import random
from pathlib import Path

from chemlab.evidence.reaction_library import file_digest, reaction_input
from chemlab.records import canonical_bytes, digest
from chemlab.store import IntegrityError


def map_requests(requests: list[dict], manifest: dict) -> dict:
    import numpy as np
    import rxnmapper
    import torch
    from rxnmapper import RXNMapper

    if len(requests) > 1000:
        raise ValueError("Mapping batches are limited to 1000 reactions")
    if manifest.get("provider") != "rxnmapper" or manifest.get("version") != "0.4.2":
        raise IntegrityError("Unsupported mapping provider manifest")
    if importlib.metadata.version("rxnmapper") != manifest["version"]:
        raise IntegrityError("Mapping provider version differs from manifest")
    model = Path(rxnmapper.__file__).parent / "models/transformers/albert_heads_8_uspto_all_1310k"
    for name, expected in manifest["artifacts"].items():
        if Path(name).name != name or file_digest(model / name) != expected:
            raise IntegrityError("Mapping artifact hash mismatch")
    settings = manifest["settings"]
    if settings != {
        "seed": 0,
        "device": "cpu",
        "dtype": "float32",
        "torch_deterministic_algorithms": True,
        "threads": 2,
    }:
        raise ValueError("Unsupported mapping execution settings")
    random.seed(settings["seed"])
    np.random.seed(settings["seed"])
    torch.manual_seed(settings["seed"])
    torch.set_num_threads(settings["threads"])
    torch.use_deterministic_algorithms(True)
    mapper = RXNMapper(config={"model_path": str(model)})
    mapper.model.to(device="cpu", dtype=torch.float32)
    mapper.model.eval()
    results = []
    for request in requests:
        query = reaction_input(request["product"], tuple(request["precursors"]))
        raw = None
        try:
            effective = ".".join(query["precursors"]) + ">>" + query["product"]
            tokens = mapper.tokenizer.encode(effective, add_special_tokens=True, truncation=False)
            if len(tokens) > mapper.model.config.max_position_embeddings:
                raise ValueError("Reaction exceeds the mapping model context; truncation forbidden")
            raw = mapper.get_attention_guided_atom_maps([effective])
            if len(raw) != 1 or not raw[0].get("mapped_rxn"):
                raise ValueError("Mapper did not return one complete prediction")
            results.append(
                {
                    "input_key": digest(query),
                    "input": query,
                    "effective_input": effective,
                    "status": "ok",
                    "raw_prediction": raw[0],
                    "raw_output": raw,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "input_key": digest(query),
                    "input": query,
                    "status": "error",
                    "error": str(exc),
                    "raw_output": raw,
                }
            )
    return {
        "provider_manifest": manifest,
        "provider_ref": digest(manifest),
        "runtime": {
            name: importlib.metadata.version(name)
            for name in (
                "rxnmapper",
                "torch",
                "transformers",
                "rdkit",
                "tokenizers",
                "numpy",
                "setuptools",
            )
        },
        "results": results,
        "limitation": "Fresh neural inference is not guaranteed bit-identical across runtimes",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("requests", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("configs/mapping/rxnmapper.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Mapping predictions are immutable")
    result = map_requests(
        json.loads(args.requests.read_bytes()), json.loads(args.manifest.read_bytes())
    )
    with args.output.open("xb") as stream:
        stream.write(canonical_bytes(result))


if __name__ == "__main__":
    main()
