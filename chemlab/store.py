from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from chemlab.records import canonical_bytes, digest


class IntegrityError(ValueError):
    pass


class Store:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "index.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS artifacts (
                    ref TEXT PRIMARY KEY, kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS adapter_predictions (
                    ref TEXT PRIMARY KEY REFERENCES artifacts(ref));
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY, ref TEXT NOT NULL REFERENCES artifacts(ref));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, target TEXT NOT NULL,
                    config_ref TEXT NOT NULL, bundle TEXT, error TEXT);
            """)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def put(self, kind: str, payload: Any, *, adapter_prediction: bool = False) -> str:
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        envelope = {"kind": kind, "schema_version": 1, "payload": payload}
        data = canonical_bytes(envelope)
        ref = hashlib.sha256(data).hexdigest()
        path = self.objects / f"{ref}.json"
        fd, temp = tempfile.mkstemp(dir=self.objects, suffix=".partial")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                if os.name == "nt":
                    os.rename(temp, path)
                else:
                    os.link(temp, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise IntegrityError("Existing artifact does not match its hash") from None
        finally:
            Path(temp).unlink(missing_ok=True)
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?)", (ref, kind))
            if adapter_prediction:
                conn.execute("INSERT OR IGNORE INTO adapter_predictions VALUES (?)", (ref,))
        return ref

    def get(self, ref: str, kind: str | None = None) -> Any:
        if not re.fullmatch(r"[0-9a-f]{64}", ref):
            raise IntegrityError("Invalid artifact reference")
        try:
            data = (self.objects / f"{ref}.json").read_bytes()
        except FileNotFoundError as exc:
            raise IntegrityError(f"Missing artifact: {ref}") from exc
        if hashlib.sha256(data).hexdigest() != ref:
            raise IntegrityError("Artifact hash mismatch")
        envelope = json.loads(data)
        if envelope.get("schema_version") != 1:
            raise IntegrityError("Unsupported artifact schema")
        if kind is not None and envelope.get("kind") != kind:
            raise IntegrityError("Artifact type mismatch")
        return envelope["payload"]

    def prediction(self, ref: str) -> Any:
        with self.connect() as conn:
            registered = conn.execute(
                "SELECT 1 FROM adapter_predictions WHERE ref=?", (ref,)
            ).fetchone()
        if not registered:
            raise IntegrityError("Prediction did not originate inside the adapter boundary")
        return self.get(ref, "prediction")

    def cache_get(self, key: Any) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT ref FROM cache WHERE key=?", (digest(key),)).fetchone()
        if row is None:
            return None
        self.get(row[0])
        return str(row[0])

    def cache_put(self, key: Any, ref: str) -> None:
        self.get(ref)
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO cache VALUES (?,?)", (digest(key), ref))
