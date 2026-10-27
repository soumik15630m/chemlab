from __future__ import annotations

from pathlib import Path
from typing import Any

from chemlab.adapters.models import ModelService
from chemlab.adapters.sdk import validate_files
from chemlab.records import ModelManifest, canonical_bytes
from chemlab.store import Store


class Registry:
    def __init__(self, store: Store):
        self.store = store
        with store.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS registry (
                alias TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL)""")

    def register_model(self, alias: str, manifest: ModelManifest) -> str:
        validate_files(manifest)
        ref = self.store.put("model_manifest", manifest)
        self.register(alias, "model_manifest", ref)
        return ref

    def register(self, alias: str, kind: str, ref: str) -> None:
        if not alias or not all(c.isalnum() or c in "-_." for c in alias):
            raise ValueError("Alias must contain only letters, numbers, '-', '_' and '.'")
        self.store.get(ref, kind)
        with self.store.connect() as conn:
            row = conn.execute("SELECT ref FROM registry WHERE alias=?", (alias,)).fetchone()
            if row and row[0] != ref:
                raise ValueError(
                    "Alias already names another immutable artifact; choose a new versioned alias"
                )
            conn.execute("INSERT OR IGNORE INTO registry VALUES (?,?,?)", (alias, kind, ref))

    def resolve(self, alias_or_ref: str, kind: str | None = None) -> str:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT kind,ref FROM registry WHERE alias=?", (alias_or_ref,)
            ).fetchone()
        if row:
            if kind and row[0] != kind:
                raise ValueError("Registry type mismatch")
            return str(row[1])
        self.store.get(alias_or_ref, kind)
        return alias_or_ref

    def list(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute("SELECT alias,kind,ref FROM registry ORDER BY alias").fetchall()
        return [
            {"alias": alias, "kind": kind, "ref": ref, "record": self.store.get(ref, kind)}
            for alias, kind, ref in rows
        ]


def load_manifest(path: str | Path) -> ModelManifest:
    return ModelManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def parity(store: Store, ref: str, inputs: list[str], count: int) -> dict[str, Any]:
    from chemlab.adapters.models import Backend, reaction_key
    from chemlab.records import Candidate

    service = ModelService(store, ref)
    backend = Backend(service.manifest)
    cases = []
    for smiles in inputs:
        effective = service.effective(smiles)
        from chemlab.adapters.models import inference_context

        with inference_context(service.manifest):
            raw = backend.predict(effective, count)
        if service.manifest.kind == "forward":
            artifact, forward_prediction = service.forward((smiles,), count)
            same = canonical_bytes(raw) == canonical_bytes(forward_prediction.raw_output)
            identities: list[Any] = [
                m.canonical_smiles for m in forward_prediction.products if m.status == "ok"
            ]
        else:
            artifact, prediction = service.backward(smiles, count)
            same = canonical_bytes(raw) == canonical_bytes(prediction.raw_output)
            identities = [
                reaction_key(c) for c in prediction.candidates if isinstance(c, Candidate)
            ]
        cases.append(
            {
                "input": smiles,
                "effective_input": effective,
                "raw_parity": same,
                "identities": identities,
                "artifact_ref": artifact,
            }
        )
    return {"manifest_ref": ref, "passed": all(c["raw_parity"] for c in cases), "cases": cases}
