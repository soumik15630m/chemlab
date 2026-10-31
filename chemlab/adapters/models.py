from __future__ import annotations

import importlib
import importlib.metadata
import json
import math
import os
import subprocess
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rdkit import Chem, rdBase
from syntheseus import BackwardReactionModel, Bag, SingleProductReaction
from syntheseus import Molecule as SMolecule

from chemlab.adapters.sdk import PredictionProvider, validate_files, validate_tokenization
from chemlab.chemistry import require_molecule, require_stable_molecule
from chemlab.records import (
    Candidate,
    CandidateError,
    ForwardEvidence,
    ModelManifest,
    Prediction,
    canonical_bytes,
    digest,
)
from chemlab.store import Store

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}
_inference_lock = threading.RLock()


class OrderedMoleculeSet(set[SMolecule]):
    def __iter__(self):
        return iter(sorted(super().__iter__(), key=lambda mol: mol.smiles))


class DeterministicReaction(SingleProductReaction):
    @property
    def unique_reactants(self) -> set[SMolecule]:
        return OrderedMoleculeSet(super().unique_reactants)


@contextmanager
def inference_context(manifest: ModelManifest):
    import random

    import numpy as np

    with _inference_lock:
        if manifest.determinism == "stochastic":
            yield
            return
        python_state, numpy_state = random.getstate(), np.random.get_state()
        random.seed(manifest.inference_seed)
        np.random.seed(manifest.inference_seed % (2**32))
        try:
            if manifest.backend == "syntheseus":
                import torch

                devices = (
                    list(range(torch.cuda.device_count())) if torch.cuda.is_available() else []
                )
                previous = torch.are_deterministic_algorithms_enabled()
                try:
                    torch.use_deterministic_algorithms(True)
                    with torch.random.fork_rng(devices=devices):
                        torch.manual_seed(manifest.inference_seed)
                        with torch.inference_mode():
                            yield
                finally:
                    torch.use_deterministic_algorithms(previous)
            else:
                yield
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)


def request_lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def score_cost(score: float, manifest: ModelManifest) -> float:
    if not math.isfinite(score):
        raise ValueError("Non-finite model score")
    if manifest.score_semantics == "probability":
        if not 0 < score <= 1:
            raise ValueError("Probability must be in (0, 1]; zero candidates are excluded")
        return -math.log(score)
    if score < 0:
        raise ValueError("Negative search costs are unsupported")
    return score


def reaction_key(candidate: Candidate) -> tuple[str, tuple[str, ...]]:
    return candidate.product.canonical_smiles, tuple(
        sorted({p.canonical_smiles for p in candidate.precursors})
    )


def error_source(value: Any) -> Any:
    try:
        canonical_bytes(value)
        return value
    except (TypeError, ValueError):
        return {"encoding": "python-repr-of-noncanonical-output", "source": repr(value)}


class Backend:
    def __init__(self, manifest: ModelManifest):
        self.manifest = manifest
        self.native: Any = None
        self.replay: Any = None
        if manifest.backend == "replay":
            path = Path(str(manifest.replay_file))
            self.replay = json.loads(path.read_text(encoding="utf-8"))
            if digest(self.replay) != manifest.checkpoint_hash:
                raise ValueError("Replay artifact does not match its checkpoint hash")
        elif manifest.backend == "syntheseus":
            validate_files(manifest)
            module, name = str(manifest.model_class).rsplit(":", 1)
            cls = getattr(importlib.import_module(module), name)
            self.native = cls(
                model_dir=manifest.checkpoint,
                device=manifest.device,
                remove_duplicates=False,
                **manifest.decoding,
            )
        elif manifest.backend == "python":
            validate_files(manifest)
            module, name = str(manifest.model_class).rsplit(":", 1)
            self.native = getattr(importlib.import_module(module), name)(manifest)
            if not isinstance(self.native, PredictionProvider):
                raise ValueError("Python provider must implement predict(input, num_results)")
        else:
            validate_files(manifest)

    def predict(self, effective_input: str, count: int) -> Any:
        manifest = self.manifest
        if manifest.backend == "replay":
            return self.replay.get(effective_input, [])[:count]
        if manifest.backend == "command":
            result = subprocess.run(
                list(manifest.command),
                input=canonical_bytes(
                    {
                        "input": effective_input,
                        "num_results": count,
                        "manifest": manifest.model_dump(mode="json"),
                    }
                ),
                capture_output=True,
                timeout=manifest.timeout_seconds,
                check=True,
                shell=False,
            )
            response = json.loads(result.stdout)
            if response.get("effective_input") != effective_input:
                raise ValueError("Backend input binding mismatch")
            return response["predictions"]
        if manifest.backend == "python":
            return self.native.predict(effective_input, count)
        tokenizer = getattr(getattr(self.native, "model", None), "tokenizer", None)
        if tokenizer is not None:
            validate_tokenization(tokenizer, effective_input, self.native.model.max_seq_len)
        if manifest.kind == "forward":
            molecules = Bag([SMolecule(s) for s in effective_input.split(".")])
            predictions = self.native([molecules], num_results=count)[0]
            return [
                {"product": ".".join(m.smiles for m in r.products), "metadata": r.metadata}
                for r in predictions
            ]
        predictions = self.native([SMolecule(effective_input)], num_results=count)[0]
        return [
            {
                "precursors": [m.smiles for m in r.reactants],
                "score": r.metadata["probability"],
                "metadata": r.metadata,
            }
            for r in predictions
        ]


class ModelService:
    def __init__(self, store: Store, manifest_ref: str):
        self.store = store
        self.manifest_ref = manifest_ref
        self.manifest = ModelManifest.model_validate(store.get(manifest_ref, "model_manifest"))
        self.backend: Backend | None = None
        self.actual_inferences = 0
        self.cache_hits = 0

    def effective(self, smiles: str) -> str:
        mol = require_stable_molecule(smiles)
        molecule = Chem.MolFromSmiles(mol.canonical_smiles)
        supported = self.manifest.supported_atomic_numbers
        if supported and any(a.GetAtomicNum() not in supported for a in molecule.GetAtoms()):
            raise ValueError("unsupported_input: model manifest does not support an element")
        if self.manifest.preprocessing == "remove_stereo":
            Chem.RemoveStereochemistry(molecule)
            return Chem.MolToSmiles(molecule)
        return mol.canonical_smiles

    def settings(self) -> dict[str, Any]:
        packages = {"syntheseus": importlib.metadata.version("syntheseus")}
        if self.manifest.backend == "syntheseus":
            for package in ("torch", "retrochimera", "pytorch-lightning"):
                try:
                    packages[package] = importlib.metadata.version(package)
                except importlib.metadata.PackageNotFoundError:
                    packages[package] = "not_installed"
        return {
            "adapter_policy": "adapter-v1",
            "manifest_ref": self.manifest_ref,
            "rdkit": rdBase.rdkitVersion,
            "dtype": self.manifest.dtype,
            "device": self.manifest.device,
            "decoding": self.manifest.decoding,
            "template_settings": self.manifest.template_settings,
            "inference_seed": self.manifest.inference_seed,
            "determinism": self.manifest.determinism,
            "provider_version": self.manifest.provider_version,
            "runtime_packages": packages,
            "thread_environment": {
                name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS")
            },
        }

    def _raw(self, effective: str, count: int) -> Any:
        with inference_context(self.manifest):
            if self.backend is None:
                self.backend = Backend(self.manifest)
            self.actual_inferences += 1
            return self.backend.predict(effective, count)

    def backward(self, smiles: str, count: int) -> tuple[str, Prediction]:
        effective = self.effective(smiles)
        key = {
            "operation": "backward",
            "input": effective,
            "count": count,
            "settings": self.settings(),
        }
        if self.manifest.determinism == "stochastic":
            key["realization"] = uuid.uuid4().hex
        with request_lock(digest(key)):
            cached = self.store.cache_get(key)
            if cached:
                prediction = Prediction.model_validate(self.store.prediction(cached))
                if (
                    prediction.manifest_ref != self.manifest_ref
                    or prediction.effective_input != effective
                    or prediction.requested_count != count
                ):
                    raise ValueError("Cache prediction binding mismatch")
                self.cache_hits += 1
                return cached, prediction
            raw: Any = None
            candidates: list[Candidate | CandidateError] = []
            try:
                raw = self._raw(effective, count)
                canonical_bytes(raw)
                if not isinstance(raw, list) or len(raw) > count:
                    raise ValueError("Prediction list violates the requested output count")
                for index, item in enumerate(raw):
                    try:
                        precursors = tuple(require_stable_molecule(s) for s in item["precursors"])
                        score = float(item["score"])
                        cost = score_cost(score, self.manifest)
                        template = item.get("template_id")
                        if (
                            self.manifest.kind == "template_based"
                            and template not in self.manifest.templates
                        ):
                            raise ValueError("Missing or unbound template ID")
                        candidates.append(
                            Candidate(
                                index=index,
                                product=require_molecule(effective),
                                precursors=precursors,
                                score=score,
                                cost=cost,
                                template_id=template,
                                mapped_reaction=item.get("mapped_reaction"),
                                mapping_required=item.get("mapping_required", False),
                            )
                        )
                    except Exception as exc:
                        candidates.append(CandidateError(index=index, raw=item, error=str(exc)))
                prediction = Prediction(
                    manifest_ref=self.manifest_ref,
                    effective_input=effective,
                    requested_count=count,
                    raw_output=raw,
                    candidates=tuple(candidates),
                    status="ok",
                    settings=self.settings(),
                )
            except Exception as exc:
                prediction = Prediction(
                    manifest_ref=self.manifest_ref,
                    effective_input=effective,
                    requested_count=count,
                    raw_output=error_source(raw),
                    candidates=(),
                    status="error",
                    error=str(exc),
                    settings=self.settings(),
                )
            ref = self.store.put("prediction", prediction, adapter_prediction=True)
            if prediction.status == "ok":
                self.store.cache_put(key, ref)
            return ref, prediction

    def forward(self, precursors: tuple[str, ...], count: int) -> tuple[str, ForwardEvidence]:
        combined = ".".join(precursors)
        effective = self.effective(combined)
        key = {
            "operation": "forward",
            "input": effective,
            "count": count,
            "settings": self.settings(),
        }
        if self.manifest.determinism == "stochastic":
            key["realization"] = uuid.uuid4().hex
        with request_lock(digest(key)):
            cached = self.store.cache_get(key)
            if cached:
                result = ForwardEvidence.model_validate(self.store.get(cached, "forward_evidence"))
                if (
                    result.manifest_ref != self.manifest_ref
                    or result.effective_input != effective
                    or result.requested_count != count
                ):
                    raise ValueError("Forward cache binding mismatch")
                self.cache_hits += 1
                return cached, result
            raw: Any = None
            try:
                from chemlab.chemistry.identity import identify

                raw = self._raw(effective, count)
                canonical_bytes(raw)
                if not isinstance(raw, list) or len(raw) > count:
                    raise ValueError("Forward list violates requested output contract")
                products = tuple(identify(item["product"]) for item in raw)
                result = ForwardEvidence(
                    manifest_ref=self.manifest_ref,
                    effective_input=effective,
                    requested_count=count,
                    products=products,
                    raw_output=raw,
                    status="ok",
                    information_lost=(require_molecule(combined).canonical_smiles != effective),
                    settings=self.settings(),
                )
            except Exception as exc:
                result = ForwardEvidence(
                    manifest_ref=self.manifest_ref,
                    effective_input=effective,
                    requested_count=count,
                    products=(),
                    raw_output=error_source(raw),
                    status="error",
                    error=str(exc),
                    settings=self.settings(),
                )
            ref = self.store.put("forward_evidence", result)
            if result.status == "ok":
                self.store.cache_put(key, ref)
            return ref, result


class SearchModel(BackwardReactionModel):
    def __init__(self, service: ModelService, count: int):
        super().__init__(use_cache=True, default_num_results=count)
        self.service = service
        self.logical_expansions = 0
        self.prediction_refs: list[str] = []

    def __call__(self, inputs: list[SMolecule], num_results: int | None = None):
        self.logical_expansions += len(inputs)
        return super().__call__(inputs, num_results=num_results)

    def _get_reactions(self, inputs: list[SMolecule], num_results: int):
        batches = []
        for mol in inputs:
            ref, prediction = self.service.backward(mol.smiles, num_results)
            self.prediction_refs.append(ref)
            if prediction.status == "error":
                raise RuntimeError(prediction.error)
            best: dict[Any, Candidate] = {}
            contributors: dict[Any, list[dict[str, Any]]] = {}
            for candidate in prediction.candidates:
                if not isinstance(candidate, Candidate):
                    continue
                key = reaction_key(candidate)
                contributors.setdefault(key, []).append(
                    {"prediction_ref": ref, "index": candidate.index}
                )
                if key not in best or (candidate.cost, candidate.index) < (
                    best[key].cost,
                    best[key].index,
                ):
                    best[key] = candidate
            results = []
            for key, candidate in sorted(
                best.items(), key=lambda kv: (kv[1].cost, kv[0], kv[1].index)
            ):
                results.append(
                    DeterministicReaction(
                        product=SMolecule(require_molecule(mol.smiles).canonical_smiles),
                        reactants=Bag([SMolecule(s) for s in key[1]]),
                        metadata={
                            "chemlab_cost": candidate.cost,
                            "prediction_ref": ref,
                            "candidate_index": candidate.index,
                            "contributors": contributors[key],
                        },
                    )
                )
            batches.append(results)
        return batches
