import json

import pytest

from chemlab.adapters.models import ModelService
from chemlab.evidence.checks import import_stock
from chemlab.records import ModelManifest, RunConfig, digest
from chemlab.store import Store


@pytest.fixture
def lab(tmp_path):
    store = Store(tmp_path / "store")
    backward = {
        "CCOC(C)=O": [
            {"precursors": ["CCO", "CC(=O)O"], "score": 0.8},
            {"precursors": ["CC(=O)O", "CCO"], "score": 0.7},
        ],
    }
    forward = {"CC(=O)O.CCO": [{"product": "CCOC(C)=O"}]}

    def manifest(data, kind="template_free", **kwargs):
        file = tmp_path / f"{len(list(tmp_path.glob('*.json')))}.json"
        file.write_text(json.dumps(data), encoding="ascii")
        record = ModelManifest(
            name=f"Computational fixture {kind}",
            kind=kind,
            backend="replay",
            checkpoint=str(file),
            checkpoint_hash=digest(data),
            training_provenance="synthetic test only",
            license="test fixture",
            score_semantics="probability",
            score_direction="higher",
            replay_file=str(file),
            **kwargs,
        )
        return store.put("model_manifest", record)

    backward_ref = manifest(backward)
    forward_ref = manifest(forward, "forward")
    stock_ref = import_stock(store, ["CCO", "CC(=O)O"], "Test stock", "synthetic fixture", "test")
    config = RunConfig(
        backward_manifest=backward_ref,
        forward_manifest=forward_ref,
        stock_ref=stock_ref,
        prediction_count=10,
        forward_k=5,
        logical_expansion_limit=20,
        route_limit=10,
        max_depth=10,
        seed=0,
    )
    return (
        store,
        config,
        manifest,
        ModelService(store, backward_ref),
        ModelService(store, forward_ref),
    )


@pytest.fixture
def ester_route(lab):
    from chemlab.chemistry import require_molecule
    from chemlab.records import Occurrence, Route, Step

    _, _, _, backward, _ = lab
    ref, _ = backward.backward("CCOC(C)=O", 10)
    return Route(
        root_id="m0",
        molecules=tuple(
            Occurrence(id=f"m{i}", molecule=require_molecule(s))
            for i, s in enumerate(["CCOC(C)=O", "CCO", "CC(=O)O"])
        ),
        steps=(
            Step(
                id="s0",
                product_id="m0",
                precursor_ids=("m1", "m2"),
                prediction_ref=ref,
                candidate_index=0,
            ),
        ),
        search_cost=0.2231435513142097,
        source="computational fixture",
    )
