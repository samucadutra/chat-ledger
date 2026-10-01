# ADR 0007 — Synchronous SQLAlchemy 2 with psycopg 3

## Status

Accepted (F01, 2026-10-01)

## Context

The API serves a single local user, while the worker does CPU- and I/O-bound
batch work and needs PostgreSQL `COPY` for bulk loads. Async SQLAlchemy would
force two code paths (async API, sync worker) or async everywhere.

## Decision

Both the API and the worker use the **sync** SQLAlchemy 2 engine with the
psycopg 3 driver. FastAPI routes are plain `def` functions that run in the
threadpool. Transactions use `session_scope()` / `engine.begin()`, and adapters
can join a caller's transaction.

## Consequences

- One data-access code path, shared by the API, the worker and the tests.
- Native `COPY` support via psycopg 3 for F04 bulk ingestion.
- API concurrency is bounded by the threadpool size, which a single-user tool
  never reaches.
- Long-polling or streaming endpoints, if ever needed, would require care
  (threads, not coroutines).
