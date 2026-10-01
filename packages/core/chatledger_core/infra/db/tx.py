"""Helper letting adapters run standalone or inside a caller's transaction."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine


class TransactionalAdapter:
    def __init__(self, engine: Engine, conn: Connection | None = None) -> None:
        self._engine = engine
        self._conn = conn

    @contextmanager
    def _tx(self) -> Iterator[Connection]:
        if self._conn is not None:
            yield self._conn
            return
        with self._engine.begin() as conn:
            yield conn
