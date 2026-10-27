from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from chemlab.records import Route, VerificationReport, canonical_bytes, digest
from chemlab.store import IntegrityError, Store


def references(kind: str, payload: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    if kind == "route":
        refs.update(step["prediction_ref"] for step in payload["steps"])
    elif kind in ("prediction", "forward_evidence"):
        refs.add(payload["manifest_ref"])
    elif kind == "run_config":
        refs.update(
            payload[key]
            for key in ("backward_manifest", "forward_manifest", "stock_ref", "corpus_ref")
            if payload.get(key)
        )
    elif kind == "corpus":
        refs.update(
            payload[key]
            for key in ("source_artifact_ref", "ingestion_report_ref")
            if payload.get(key)
        )
    elif kind == "run_manifest":
        refs.update(payload.get("search", {}).get("prediction_refs", []))
        refs.update(
            payload[key]
            for key in (
                "config_ref",
                "backward_manifest_ref",
                "forward_manifest_ref",
                "stock_ref",
                "corpus_ref",
            )
            if payload.get(key)
        )
    elif kind == "verification_report":
        refs.add(payload["stock_ref"])
        refs.update(ref for check in payload["checks"] for ref in check["evidence"])
        refs.update(
            item["corpus_ref"]
            for item in payload["precedent"].values()
            if isinstance(item, dict) and item.get("corpus_ref")
        )
    return refs


def group(report: VerificationReport) -> str:
    if report.structural_status == "verified":
        return (
            "verified_consistent"
            if report.forward_status == "consistent"
            else (
                "availability"
                if report.forward_status == "not_applicable"
                else "verified_other_evidence"
            )
        )
    return report.structural_status


def publish(
    store: Store,
    run_id: str,
    run: dict[str, Any],
    evaluated: list[tuple[Route, VerificationReport]],
) -> Path:
    bundles = store.root / "bundles"
    bundles.mkdir(exist_ok=True)
    staging = bundles / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    (staging / "objects").mkdir()
    refs: set[str] = set()
    groups: dict[str, list[dict[str, str]]] = {
        key: []
        for key in (
            "verified_consistent",
            "verified_other_evidence",
            "unresolved",
            "rejected",
            "availability",
        )
    }

    def collect(ref: str):
        if ref in refs:
            return
        payload = store.get(ref)
        refs.add(ref)
        shutil.copyfile(store.objects / f"{ref}.json", staging / "objects" / f"{ref}.json")

        envelope = json.loads((store.objects / f"{ref}.json").read_bytes())
        for dependency in sorted(references(envelope["kind"], payload)):
            collect(dependency)

    for route, report in evaluated:
        if report.route_hash != digest(route):
            raise IntegrityError("Report is bound to a different route")
        route_ref = store.put("route", route)
        report_ref = store.put("verification_report", report)
        collect(route_ref)
        collect(report_ref)
        groups[group(report)].append({"route_ref": route_ref, "report_ref": report_ref})
    run_ref = store.put("run_manifest", run)
    collect(run_ref)
    completion: dict[str, Any] = {
        "schema_version": 1,
        "state": "complete",
        "run_id": run_id,
        "run_ref": run_ref,
        "groups": groups,
        "files": {f"objects/{ref}.json": ref for ref in sorted(refs)},
    }
    for name, expected in completion["files"].items():
        if hashlib.sha256((staging / name).read_bytes()).hexdigest() != expected:
            raise IntegrityError("Staged file hash mismatch")
    complete_path = staging / "complete.json"
    with complete_path.open("wb") as stream:
        stream.write(canonical_bytes(completion))
        stream.flush()
        os.fsync(stream.fileno())
    destination = bundles / run_id
    if destination.exists():
        raise FileExistsError("An existing bundle must never be overwritten")
    os.rename(staging, destination)
    read_bundle(destination)
    return destination


def read_bundle(path: Path | str) -> dict[str, Any]:
    root = Path(path).resolve()
    if root.name.startswith(".staging-"):
        raise IntegrityError("Staged bundles are not published output")
    try:
        complete = json.loads((root / "complete.json").read_text(encoding="ascii"))
    except (FileNotFoundError, ValueError) as exc:
        raise IntegrityError("Bundle has no valid completion manifest") from exc
    if complete.get("state") != "complete" or complete.get("schema_version") != 1:
        raise IntegrityError("Incomplete or unsupported bundle")
    objects = {}
    for name, expected in complete["files"].items():
        object_path = (root / name).resolve()
        if not object_path.is_relative_to(root) or name != f"objects/{expected}.json":
            raise IntegrityError("Invalid bundle object path")
        data = object_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise IntegrityError("Published bundle hash mismatch")
        objects[expected] = json.loads(data)
    if complete["run_ref"] not in objects:
        raise IntegrityError("Run manifest is absent")
    for envelope in objects.values():
        if not references(envelope["kind"], envelope["payload"]).issubset(objects):
            raise IntegrityError("Bundle has dangling artifact references")
    for category, items in complete["groups"].items():
        for item in items:
            route_obj, report_obj = objects[item["route_ref"]], objects[item["report_ref"]]
            if route_obj["kind"] != "route" or report_obj["kind"] != "verification_report":
                raise IntegrityError("Bundle route/report type mismatch")
            route = Route.model_validate(route_obj["payload"])
            report = VerificationReport.model_validate(report_obj["payload"])
            if report.route_hash != digest(route) or group(report) != category:
                raise IntegrityError("Bundle report binding/category mismatch")
    return {**complete, "objects": objects}
