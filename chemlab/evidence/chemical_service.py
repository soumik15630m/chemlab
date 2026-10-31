"""Persistent reaction/route evidence jobs, separate from baseline acceptance."""

from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from pydantic import model_validator

from chemlab.evidence.bounded import dependency_session
from chemlab.evidence.chemical_checks import POLICY, assess_reaction
from chemlab.evidence.reaction_diagnostics import diagnose_route
from chemlab.evidence.reaction_library import (
    ReactionLibrary,
    file_digest,
    index_reaction_inputs,
    reaction_input,
)
from chemlab.evidence.reaction_templates import ContextLibrary
from chemlab.records import Record, canonical_bytes, digest
from chemlab.registry import Registry
from chemlab.store import IntegrityError, Store


class KnowledgeConfig(Record):
    name: str
    source_path: str | None = None
    source_manifest: str | None = None
    context_path: str | None = None
    context_manifest: str | None = None
    mapper_command: tuple[str, ...] = ()
    mapper_manifest_path: str | None = None
    mapper_manifest_hash: str | None = None
    timeout_seconds: int = 600

    @model_validator(mode="after")
    def bindings(self):
        for path, ref in (
            (self.source_path, self.source_manifest),
            (self.context_path, self.context_manifest),
            (self.mapper_manifest_path, self.mapper_manifest_hash),
        ):
            if bool(path) != bool(ref):
                raise ValueError("Knowledge paths and hashes must be provided together")
        if self.context_path and not self.source_path:
            raise ValueError("Context evidence requires its source library")
        if bool(self.mapper_command) != bool(self.mapper_manifest_path):
            raise ValueError("Mapping commands require a bound provider manifest")
        if not 1 <= self.timeout_seconds <= 3600:
            raise ValueError("Mapping timeout must be between 1 and 3600 seconds")
        return self


def load_knowledge(config: KnowledgeConfig):
    source = (
        ReactionLibrary(Path(config.source_path), config.source_manifest)
        if config.source_path and config.source_manifest
        else None
    )
    contexts = (
        ContextLibrary(Path(config.context_path), config.context_manifest, source)
        if config.context_path and config.context_manifest and source
        else None
    )
    if config.mapper_manifest_path:
        if file_digest(Path(config.mapper_manifest_path)) != config.mapper_manifest_hash:
            raise IntegrityError("Mapping provider manifest hash mismatch")
    return source, contexts


def register_knowledge(store: Store, alias: str, config: KnowledgeConfig) -> str:
    source, contexts = load_knowledge(config)
    snapshots: dict[str, Any] = {"config": config.model_dump(mode="json")}
    if source:
        snapshots["source_manifest"] = source.manifest
    if contexts:
        snapshots["context_manifest"] = contexts.manifest
    if config.mapper_manifest_path:
        snapshots["mapper_manifest"] = json.loads(Path(config.mapper_manifest_path).read_bytes())
    ref = store.put("reaction_knowledge", snapshots)
    Registry(store).register(alias, "reaction_knowledge", ref)
    return ref


def mapping_batch(
    store: Store, queries: list[dict], config: KnowledgeConfig
) -> tuple[str | None, dict]:
    if not config.mapper_command:
        return None, {}
    manifest_path = Path(config.mapper_manifest_path or "")
    if file_digest(manifest_path) != config.mapper_manifest_hash:
        raise IntegrityError("Mapping manifest changed before inference")
    manifest = json.loads(manifest_path.read_bytes())
    with tempfile.TemporaryDirectory(prefix="chemlab-mapping-") as folder:
        request = Path(folder) / "requests.json"
        output = Path(folder) / "raw.json"
        request.write_bytes(canonical_bytes(queries))
        try:
            process = subprocess.run(
                [
                    *config.mapper_command,
                    str(request),
                    str(output),
                    "--manifest",
                    str(manifest_path),
                ],
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                check=False,
            )
            if process.returncode:
                raise RuntimeError(process.stderr[-4000:] or "Mapping worker failed")
            raw = json.loads(output.read_bytes())
        except (subprocess.TimeoutExpired, RuntimeError, OSError, ValueError) as exc:
            raw = {
                "provider_manifest": manifest,
                "provider_ref": digest(manifest),
                "results": [
                    {"input": q, "input_key": digest(q), "status": "error", "error": str(exc)}
                    for q in queries
                ],
                "worker_error": str(exc),
            }
    # Persist unmodified provider output before selecting or interpreting any map.
    ref = store.put("mapping_batch", {"requests": queries, "raw_output": raw})
    if raw.get("provider_ref") != digest(manifest) or raw.get("provider_manifest") != manifest:
        raise IntegrityError("Mapping worker provider binding differs")
    outputs = raw["results"]
    keys = [r["input_key"] for r in outputs]
    if len(set(keys)) != len(keys) or set(keys) != {digest(q) for q in queries}:
        raise IntegrityError("Mapping outputs do not correspond one-to-one with requests")
    for result in outputs:
        if result["input_key"] != digest(result["input"]):
            raise IntegrityError("Mapping output input binding mismatch")
    return ref, {r["input_key"]: r for r in outputs}


def assess_batch(
    store: Store,
    queries: list[dict],
    config: KnowledgeConfig,
    *,
    excluded: frozenset[str] = frozenset(),
    progress=None,
) -> dict:
    normalized = index_reaction_inputs(queries)
    if progress:
        progress("validating_knowledge", 0, len(normalized))
    source, contexts = load_knowledge(config)
    if progress:
        progress("mapping_reactions", 0, len(normalized))
    mapping_ref, mappings = mapping_batch(store, list(normalized.values()), config)
    with ExitStack() as stack:
        stack.enter_context(dependency_session())
        source_snapshot = stack.enter_context(source.session()) if source else None
        context_snapshot = stack.enter_context(contexts.session()) if contexts else None
        results = {}
        for key, q in normalized.items():
            results[key] = assess_reaction(
                q["product"],
                tuple(q["precursors"]),
                proposal=mappings.get(key),
                library=source_snapshot,
                contexts=context_snapshot,
                excluded=excluded,
            )
            if progress:
                progress("checking_reactions", len(results), len(normalized))
    return {"policy_hash": digest(POLICY), "mapping_batch_ref": mapping_ref, "results": results}


def summarize_route(binding: dict | None, results: dict) -> dict | None:
    if binding is None:
        return None
    steps = binding["steps"]
    if not steps or {s["input_key"] for s in steps} != set(results):
        raise IntegrityError("Route evidence must cover every selected step and no other reaction")
    counts = Counter(results[s["input_key"]]["evidence_outcome"] for s in steps)
    if counts["contradiction"]:
        outcome = "contradiction"
    elif counts["error"]:
        outcome = "error"
    elif counts["support"] == len(steps):
        outcome = "support"
    else:
        outcome = "unresolved"
    return {
        "step_occurrences": len(steps),
        "step_findings": dict(counts),
        "evidence_outcome": outcome,
        "chemical_feasibility": "unresolved",
        "limitation": (
            "Every step is required; support does not establish "
            "cross-step experimental compatibility"
        ),
    }


class ChemicalService:
    def __init__(self, store: Store):
        self.store = store
        with store.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS chemical_jobs (
                id TEXT PRIMARY KEY, state TEXT NOT NULL, request_ref TEXT NOT NULL,
                result_ref TEXT, error TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS chemical_progress (
                id TEXT PRIMARY KEY, stage TEXT NOT NULL, completed INTEGER NOT NULL,
                total INTEGER NOT NULL)""")

    def prepare(
        self, queries: list[dict], knowledge_ref: str | None, *, route_binding: dict | None = None
    ) -> str:
        if not 1 <= len(queries) <= 1000:
            raise ValueError("Chemical checks require 1 to 1000 represented reactions")
        normalized = [reaction_input(q["product"], tuple(q["precursors"])) for q in queries]
        if knowledge_ref:
            self.store.get(knowledge_ref, "reaction_knowledge")
        request = {
            "queries": normalized,
            "knowledge_ref": knowledge_ref,
            "route_binding": route_binding,
            "policy_hash": digest(POLICY),
        }
        ref = self.store.put("chemical_request", request)
        job_id = uuid.uuid4().hex
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO chemical_jobs VALUES (?,?,?,NULL,NULL)", (job_id, "queued", ref)
            )
        return job_id

    def execute(self, job_id: str) -> None:
        with self.store.connect() as conn:
            row = conn.execute(
                "UPDATE chemical_jobs SET state='running' WHERE id=? AND state='queued' "
                "RETURNING request_ref",
                (job_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Chemical job is absent or not queued")
        try:
            request = self.store.get(row[0], "chemical_request")
            if request["policy_hash"] != digest(POLICY):
                raise IntegrityError("Chemical policy changed after submission")
            config = (
                KnowledgeConfig.model_validate(
                    self.store.get(
                        request["knowledge_ref"],
                        "reaction_knowledge",
                    )["config"]
                )
                if request["knowledge_ref"]
                else KnowledgeConfig(name="Represented inputs only")
            )

            def progress(stage, completed, total):
                with self.store.connect() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO chemical_progress VALUES (?,?,?,?)",
                        (job_id, stage, completed, total),
                    )

            result = assess_batch(self.store, request["queries"], config, progress=progress)
            report = {
                "request_ref": row[0],
                "knowledge_ref": request["knowledge_ref"],
                "knowledge_name": config.name,
                **result,
                "route_binding": request["route_binding"],
                "chemical_feasibility": "unresolved",
                "counts": dict(Counter(r["evidence_outcome"] for r in result["results"].values())),
                "count_basis": "Distinct represented reaction inputs",
                "route_summary": summarize_route(request["route_binding"], result["results"]),
            }
            result_ref = self.store.put("chemical_report", report)
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE chemical_jobs SET state='complete',result_ref=? WHERE id=?",
                    (result_ref, job_id),
                )
                conn.execute("UPDATE chemical_progress SET stage='complete' WHERE id=?", (job_id,))
        except Exception as exc:
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE chemical_jobs SET state='error',error=? WHERE id=?", (str(exc), job_id)
                )

    def job(self, job_id: str) -> dict:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT state,request_ref,result_ref,error FROM chemical_jobs WHERE id=?", (job_id,)
            ).fetchone()
            progress = conn.execute(
                "SELECT stage,completed,total FROM chemical_progress WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        result = self.store.get(row[2], "chemical_report") if row[2] else None
        if result is not None:
            request = self.store.get(row[1], "chemical_request")
            if (
                result["request_ref"] != row[1]
                or result["route_binding"] != request["route_binding"]
            ):
                raise IntegrityError("Chemical job report belongs to another request or route")
            if result["policy_hash"] != request["policy_hash"]:
                raise IntegrityError("Chemical report policy differs from its request")
            if result["knowledge_ref"] != request["knowledge_ref"]:
                raise IntegrityError("Chemical report knowledge differs from its request")
            if "route_summary" in result and result["route_summary"] != summarize_route(
                request["route_binding"], result["results"]
            ):
                raise IntegrityError("Chemical route summary differs from required step findings")
            expected = index_reaction_inputs(request["queries"])
            if set(result["results"]) != set(expected) or any(
                result["results"][key]["input"] != query for key, query in expected.items()
            ):
                raise IntegrityError("Chemical job report does not cover its exact inputs")
        return {
            "id": job_id,
            "state": row[0],
            "request_ref": row[1],
            "result_ref": row[2],
            "error": row[3],
            "progress": {"stage": progress[0], "completed": progress[1], "total": progress[2]}
            if progress
            else None,
            "result": result,
        }

    def jobs(self) -> list[dict]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id,state,request_ref FROM chemical_jobs ORDER BY rowid DESC LIMIT 20"
            ).fetchall()
        return [
            {"id": job_id, "state": state, "request": self.store.get(ref, "chemical_request")}
            for job_id, state, ref in rows
        ]

    def replay(self, job_id: str) -> dict:
        job = self.job(job_id)
        if job["state"] != "complete":
            raise ValueError("Only complete chemical reports can be replayed")
        request = self.store.get(job["request_ref"], "chemical_request")
        report = job["result"]
        if report["policy_hash"] != digest(POLICY):
            raise IntegrityError("Replay requires the original chemical evidence policy")
        config = (
            KnowledgeConfig.model_validate(
                self.store.get(
                    request["knowledge_ref"],
                    "reaction_knowledge",
                )["config"]
            )
            if request["knowledge_ref"]
            else KnowledgeConfig(name="Represented inputs only")
        )
        mappings = {}
        if report["mapping_batch_ref"]:
            batch = self.store.get(report["mapping_batch_ref"], "mapping_batch")
            if batch["requests"] != list(index_reaction_inputs(request["queries"]).values()):
                raise IntegrityError("Saved mapping batch differs from requested inputs")
            raw = batch["raw_output"]
            manifest = json.loads(Path(config.mapper_manifest_path or "").read_bytes())
            if raw["provider_manifest"] != manifest or raw["provider_ref"] != digest(manifest):
                raise IntegrityError("Saved mapping provider differs from pinned replay provider")
            mappings = {entry["input_key"]: entry for entry in raw["results"]}
            if len(mappings) != len(raw["results"]) or set(mappings) != {
                digest(q) for q in batch["requests"]
            }:
                raise IntegrityError("Saved mapping batch does not cover its exact requests")
        source, contexts = load_knowledge(config)
        with ExitStack() as stack:
            stack.enter_context(dependency_session())
            source_snapshot = stack.enter_context(source.session()) if source else None
            context_snapshot = stack.enter_context(contexts.session()) if contexts else None
            replayed = {
                digest(q): assess_reaction(
                    q["product"],
                    tuple(q["precursors"]),
                    proposal=mappings.get(digest(q)),
                    library=source_snapshot,
                    contexts=context_snapshot,
                )
                for q in request["queries"]
            }
        equivalent = canonical_bytes(replayed) == canonical_bytes(report["results"])
        return {
            "report_ref": job["result_ref"],
            "request_ref": job["request_ref"],
            "replayed_results": replayed,
            "equivalent": equivalent,
            "fresh_model_inference": False,
            "chemical_feasibility": "unresolved",
            "scope": "Replay against pinned source indexes and saved raw mapping proposals",
        }


def route_queries(bundle: dict, route_ref: str) -> tuple[list[dict], dict]:
    observations = diagnose_route(bundle, route_ref)
    queries = [
        {"product": step["product"], "precursors": step["precursors"]}
        for step in observations["steps"]
    ]
    binding = {
        "route_ref": route_ref,
        "report_ref": observations["report_ref"],
        "target": observations["target"],
        "steps": [
            {
                "step_id": step["step_id"],
                "input_key": digest(reaction_input(step["product"], tuple(step["precursors"]))),
                "prediction_ref": step["prediction_ref"],
                "candidate_index": step["candidate_index"],
            }
            for step in observations["steps"]
        ],
    }
    return queries, binding


def parse_reaction(smiles: str) -> dict:
    if not 1 <= len(smiles) <= 32768:
        raise ValueError("Reaction SMILES must contain 1 to 32768 characters")
    left, agents, product = smiles.split(">")
    if agents:
        raise ValueError("Supply reactants>>product; conditions and agent fields are excluded")
    return reaction_input(product, tuple(left.split(".")))
