from __future__ import annotations

import importlib.metadata
import platform
import threading
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from chemlab.adapters.models import ModelService
from chemlab.chemistry import require_molecule
from chemlab.evidence.checks import load_stock
from chemlab.planning import search
from chemlab.records import ModelManifest, RunConfig
from chemlab.reporting.bundles import publish, read_bundle
from chemlab.store import Store
from chemlab.verification import verify


class Application:
    def __init__(self, store: Store):
        self.store = store
        self._worker_lock = threading.Lock()
        self._models: dict[str, ModelService] = {}

    def model(self, ref: str) -> ModelService:
        if ref not in self._models:
            self._models[ref] = ModelService(self.store, ref)
        return self._models[ref]

    def prepare(self, target: str, config: RunConfig) -> str:
        target = require_molecule(target).canonical_smiles
        backward = ModelManifest.model_validate(
            self.store.get(config.backward_manifest, "model_manifest")
        )
        if backward.kind == "forward":
            raise ValueError("Backward search requires a retrosynthesis model")
        if backward.determinism == "stochastic":
            raise ValueError(
                "Baseline search requires a fixed realization; "
                "independent stochastic search is not configured"
            )
        if backward.preprocessing != "identity":
            raise ValueError(
                "Information-losing backward preprocessing is unsupported by the baseline"
            )
        if config.forward_manifest:
            forward = ModelManifest.model_validate(
                self.store.get(config.forward_manifest, "model_manifest")
            )
            if forward.kind != "forward":
                raise ValueError("Forward checks require a forward model")
        load_stock(self.store, config.stock_ref)
        if config.corpus_ref:
            corpus = self.store.get(config.corpus_ref, "corpus")
            if corpus["partition"] == "final_reference":
                raise ValueError("Final-reference corpus is not available to planning/evidence")
        config_ref = self.store.put("run_config", config)
        run_id = uuid.uuid4().hex
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?)",
                (run_id, "queued", target, config_ref, None, None),
            )
        return run_id

    def execute(self, run_id: str) -> None:
        with self._worker_lock:
            with self.store.connect() as conn:
                row = conn.execute(
                    "UPDATE runs SET state='running' WHERE id=? AND state='queued' "
                    "RETURNING target, config_ref",
                    (run_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("Run is absent or is not queued")
            target, config_ref = row
            try:
                config = RunConfig.model_validate(self.store.get(config_ref, "run_config"))
                backward = self.model(config.backward_manifest)
                backward.actual_inferences = backward.cache_hits = 0
                forward = self.model(config.forward_manifest) if config.forward_manifest else None
                if forward:
                    forward.actual_inferences = forward.cache_hits = 0
                result = search(target, config, backward, load_stock(self.store, config.stock_ref))
                evaluated = [
                    (
                        route,
                        verify(self.store, route.model_dump(mode="json"), target, config, forward),
                    )
                    for route in result.routes
                ]
                versions = {
                    name: importlib.metadata.version(name)
                    for name in ("rdkit", "rdchiral", "syntheseus", "pydantic", "fastapi")
                }
                run = {
                    "target": target,
                    "config_ref": config_ref,
                    "backward_manifest_ref": config.backward_manifest,
                    "forward_manifest_ref": config.forward_manifest,
                    "stock_ref": config.stock_ref,
                    "corpus_ref": config.corpus_ref,
                    "search": result.model_dump(mode="json"),
                    "software": {**versions, "python": platform.python_version()},
                    "backward_execution": backward.settings(),
                    "forward_execution": forward.settings() if forward else None,
                    "forward_statistics": {
                        "actual_inferences": forward.actual_inferences if forward else 0,
                        "cache_hits": forward.cache_hits if forward else 0,
                    },
                    "completed_at": datetime.now(UTC).isoformat(),
                    "experimental": backward.manifest.backend == "replay",
                    "counts": dict(Counter(r.structural_status for _, r in evaluated)),
                }
                bundle = publish(self.store, run_id, run, evaluated)
                with self.store.connect() as conn:
                    conn.execute(
                        "UPDATE runs SET state=?, bundle=? WHERE id=?",
                        ("complete", str(bundle), run_id),
                    )
            except Exception as exc:
                with self.store.connect() as conn:
                    conn.execute(
                        "UPDATE runs SET state='error', error=? WHERE id=?", (str(exc), run_id)
                    )

    def runs(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            return [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY rowid DESC")]

    def run(self, run_id: str) -> dict[str, Any]:
        rows = [row for row in self.runs() if row["id"] == run_id]
        if not rows:
            raise KeyError(run_id)
        row = rows[0]
        if row["state"] == "complete":
            row["result"] = read_bundle(row["bundle"])
        return row
