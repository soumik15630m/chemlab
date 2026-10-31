"""Interruptible dependency calls; worker timeout/error is never a successful check."""

from __future__ import annotations

import multiprocessing
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pebble import ProcessPool

DEADLINE_SECONDS = 10
_pool: ContextVar[Any] = ContextVar("chemical_dependency_pool", default=None)


@contextmanager
def dependency_session():
    if _pool.get() is not None:
        yield
        return
    with ProcessPool(max_workers=1, context=multiprocessing.get_context("spawn")) as pool:
        token = _pool.set(pool)
        try:
            yield
        finally:
            _pool.reset(token)


def dependency_call(function, args: tuple, *, timeout: float = DEADLINE_SECONDS) -> dict:
    with dependency_session():
        try:
            return _pool.get().schedule(function, args=args, timeout=timeout).result()
        except TimeoutError:
            return {
                "status": "error",
                "reason": "dependency_operation_timeout",
                "timeout_seconds": timeout,
            }
        except Exception as exc:
            return {"status": "error", "reason": "dependency_worker_error", "error": str(exc)}
