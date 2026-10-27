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
from chemlab.chemistry import require_molecule
from chemlab.evidence.checks import import_stock
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


def create_app(root: Path | str = "var") -> FastAPI:
    store = Store(root)
    application = Application(store)
    registry = Registry(store)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chemlab")

    @asynccontextmanager
    async def lifespan(app):
        with store.connect() as conn:
            conn.execute(
                "UPDATE runs SET state='error', error='interrupted_before_completion' "
                "WHERE state IN ('running','queued')"
            )
        yield
        executor.shutdown(wait=True)

    app = FastAPI(title="ChemLab", version="0.1.0", lifespan=lifespan)
    app.state.application = application
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

    @app.post("/api/stocks", status_code=201)
    def stock(body: StockRequest):
        ref = import_stock(store, list(body.smiles), body.alias, body.source, body.license)
        registry.register(body.alias, "stock", ref)
        return {"ref": ref}

    @app.get("/api/molecule.svg")
    def molecule(smiles: Annotated[str, Query(min_length=1, max_length=4096)]):
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D

        identity = require_molecule(smiles)
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
