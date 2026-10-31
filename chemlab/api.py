from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from chemlab.application import Application
from chemlab.chemistry import require_stable_molecule
from chemlab.evidence.checks import import_stock
from chemlab.evidence.chemical_service import ChemicalService, parse_reaction, route_queries
from chemlab.records import Record, RunConfig
from chemlab.registry import Registry
from chemlab.store import IntegrityError, Store


class RunRequest(Record):
    target: str = Field(min_length=1, max_length=4096)
    config: RunConfig


class StockRequest(Record):
    alias: str = Field(min_length=1, max_length=100)
    smiles: tuple[str, ...] = Field(min_length=1, max_length=100000)
    source: str
    license: str


class ChemicalRequest(Record):
    reaction_smiles: str = Field(min_length=1, max_length=32768)
    knowledge_ref: str | None = None


class RouteChemicalRequest(Record):
    knowledge_ref: str | None = None


def create_app(root: Path | str = "var") -> FastAPI:
    store = Store(root)
    application = Application(store)
    chemical_service = ChemicalService(store)
    registry = Registry(store)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chemlab")

    @asynccontextmanager
    async def lifespan(app):
        with store.connect() as conn:
            conn.execute(
                "UPDATE runs SET state='error', error='interrupted_before_completion' "
                "WHERE state IN ('running','queued')"
            )
            conn.execute(
                "UPDATE chemical_jobs SET state='error', error='interrupted_before_completion' "
                "WHERE state IN ('running','queued')"
            )
        yield
        executor.shutdown(wait=True)

    app = FastAPI(title="ChemLab", version="0.1.0", lifespan=lifespan)
    app.state.application = application
    app.state.chemical_service = chemical_service
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
                return Response("Origin is not allowed", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(IntegrityError)
    async def corrupt(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "planner": "Syntheseus Retro*", "identity": "identity-v1"}

    @app.get("/api/registry")
    def registered():
        rows = registry.list()
        for row in rows:
            record = row["record"]
            if row["kind"] == "stock":
                row["record"] = {k: v for k, v in record.items() if k != "identities"}
                row["record"]["count"] = len(record["identities"])
            if row["kind"] == "corpus":
                row["record"] = {k: v for k, v in record.items() if k != "records"}
                row["record"]["count"] = len(record["records"])
        return rows

    @app.get("/api/runs")
    def runs():
        return application.runs()

    @app.post("/api/runs", status_code=202)
    def start_run(body: RunRequest):
        run_id = application.prepare(body.target, body.config)
        executor.submit(application.execute, run_id)
        return {"id": run_id, "state": "queued"}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return application.run(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc

    @app.get("/api/runs/{run_id}/bundle")
    def bundle(run_id: str):
        try:
            row = application.run(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc
        if row["state"] != "complete":
            raise HTTPException(409, "Run has no complete bundle")
        data = io.BytesIO()
        root_path = Path(row["bundle"])
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(root_path / "complete.json", "complete.json")
            for name in sorted(row["result"]["files"]):
                archive.write(root_path / name, name)
        data.seek(0)
        return StreamingResponse(
            data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="chemlab-{run_id}.zip"'},
        )

    def completed_bundle(run_id: str):
        row = get_run(run_id)
        if row["state"] != "complete":
            raise HTTPException(409, "Run has no complete published output")
        return row["result"]

    @app.post("/api/reactions/check", status_code=202)
    def check_reaction(body: ChemicalRequest):
        ref = (
            registry.resolve(body.knowledge_ref, "reaction_knowledge")
            if body.knowledge_ref
            else None
        )
        job_id = chemical_service.prepare([parse_reaction(body.reaction_smiles)], ref)
        executor.submit(chemical_service.execute, job_id)
        return {"id": job_id, "state": "queued"}

    @app.post("/api/runs/{run_id}/routes/{route_ref}/chemical-checks", status_code=202)
    def check_route_chemistry(run_id: str, route_ref: str, body: RouteChemicalRequest):
        try:
            queries, binding = route_queries(completed_bundle(run_id), route_ref)
        except KeyError as exc:
            raise HTTPException(404, "Route is not part of this completed run") from exc
        ref = (
            registry.resolve(body.knowledge_ref, "reaction_knowledge")
            if body.knowledge_ref
            else None
        )
        binding["run_id"] = run_id
        job_id = chemical_service.prepare(queries, ref, route_binding=binding)
        executor.submit(chemical_service.execute, job_id)
        return {"id": job_id, "state": "queued"}

    @app.get("/api/chemical-jobs/{job_id}")
    def chemical_job(job_id: str):
        try:
            return chemical_service.job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Chemical check job not found") from exc

    @app.get("/api/chemical-jobs")
    def chemical_jobs():
        return chemical_service.jobs()

    @app.get("/api/chemical-jobs/{job_id}/report.json")
    def chemical_report(job_id: str):
        from chemlab.records import canonical_bytes

        job = chemical_job(job_id)
        if job["state"] != "complete":
            raise HTTPException(409, "Chemical evidence report is incomplete")
        result = job["result"]
        references = {job["request_ref"]: "chemical_request", job["result_ref"]: "chemical_report"}
        if result["mapping_batch_ref"]:
            references[result["mapping_batch_ref"]] = "mapping_batch"
        if result["knowledge_ref"]:
            references[result["knowledge_ref"]] = "reaction_knowledge"
        objects = {
            ref: {"kind": kind, "schema_version": 1, "payload": store.get(ref, kind)}
            for ref, kind in references.items()
        }
        return Response(
            canonical_bytes({"job": job, "objects": objects}),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="chemlab-chemistry-{job_id}.json"'
            },
        )

    @app.get("/api/chemical-jobs/{job_id}/report.pdf")
    def chemical_pdf(job_id: str):
        from chemlab.reporting.chemical_exports import evidence_pdf

        job = chemical_job(job_id)
        if job["state"] != "complete":
            raise HTTPException(409, "Chemical evidence report is incomplete")
        return Response(
            evidence_pdf(job),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="chemlab-chemistry-{job_id}.pdf"'
            },
        )

    @app.get("/api/chemical-jobs/{job_id}/chemistry.zip")
    def chemical_structures(job_id: str):
        from chemlab.reporting.chemical_exports import evidence_chemistry_zip

        job = chemical_job(job_id)
        if job["state"] != "complete":
            raise HTTPException(409, "Chemical evidence report is incomplete")
        return Response(
            evidence_chemistry_zip(job),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="chemlab-chemistry-{job_id}.zip"'
            },
        )

    @app.get("/api/runs/{run_id}/report.pdf")
    def pdf_report(run_id: str):
        from chemlab.reporting.pdf import report_pdf

        data = report_pdf(completed_bundle(run_id))
        return Response(
            data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="chemlab-{run_id}.pdf"',
            },
        )

    @app.get("/api/runs/{run_id}/routes/{route_ref}/chemistry.zip")
    def chemistry_files(run_id: str, route_ref: str):
        from chemlab.reporting.formats import chemistry_zip

        try:
            data = chemistry_zip(completed_bundle(run_id), route_ref)
        except KeyError as exc:
            raise HTTPException(404, "Route is not part of this run") from exc
        return Response(
            data,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="chemlab-{run_id}-{route_ref[:12]}-chemistry.zip"'
                ),
            },
        )

    @app.get("/api/runs/{run_id}/routes/{route_ref}/observations.json")
    def reaction_observations(run_id: str, route_ref: str):
        from chemlab.evidence.reaction_diagnostics import diagnose_route
        from chemlab.records import canonical_bytes

        try:
            observations = diagnose_route(completed_bundle(run_id), route_ref)
        except KeyError as exc:
            raise HTTPException(404, "Route or required evidence is absent") from exc
        return Response(
            canonical_bytes(observations),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="chemlab-{run_id}-{route_ref[:12]}-observations.json"'
                ),
            },
        )

    @app.get("/api/molecule.mol")
    def mol_file(smiles: Annotated[str, Query(min_length=1, max_length=4096)]):
        from chemlab.reporting.formats import molecule_mol

        return Response(
            molecule_mol(smiles),
            media_type="chemical/x-mdl-molfile",
            headers={
                "Content-Disposition": 'attachment; filename="molecule.mol"',
            },
        )

    @app.get("/api/molecule.pdf")
    def molecule_report(smiles: Annotated[str, Query(min_length=1, max_length=4096)]):
        from chemlab.reporting.pdf import molecule_pdf

        return Response(
            molecule_pdf(smiles),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="molecule.pdf"',
            },
        )

    @app.post("/api/stocks", status_code=201)
    def stock(body: StockRequest):
        ref = import_stock(store, list(body.smiles), body.alias, body.source, body.license)
        registry.register(body.alias, "stock", ref)
        return {"ref": ref}

    @app.get("/api/molecule.svg")
    def molecule(smiles: Annotated[str, Query(min_length=1, max_length=4096)]):
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D

        identity = require_stable_molecule(smiles)
        mol = Chem.MolFromSmiles(identity.canonical_smiles)
        drawer = rdMolDraw2D.MolDraw2DSVG(360, 180)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return Response(drawer.GetDrawingText(), media_type="image/svg+xml")

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    return app
