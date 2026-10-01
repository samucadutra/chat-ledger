# ADR 0001 — PostgreSQL as the job queue

## Status

Accepted (F01, 2026-10-01)

## Context

ChatLedger runs long, restartable work — generating synthetic exports, parsing
work units, building exports and run diffs — on a pool of worker processes.
The PoC is a single-user, local `docker compose` deployment. Every extra piece
of infrastructure (Redis, RabbitMQ, Celery) adds a service to boot, monitor and
explain, and a second source of truth that can disagree with the database about
what has been processed.

## Decision

Jobs live in a PostgreSQL `job` table and are claimed with
`SELECT … FOR UPDATE SKIP LOCKED LIMIT 1`, ordered by `(priority, created_at)`.

- A claim sets a 60 s lease (`lease_owner`, `lease_expires_at`) and increments
  `attempts`; the worker renews it every 20 s while the handler runs.
- `fail` requeues with linear backoff (`5 s × attempts`) until `max_attempts`
  (3), then marks the job `failed`.
- Every worker sweeps every 15 s for expired leases and for leases held by
  workers whose heartbeat is older than 30 s (crash recovery).
- Workers poll every 1 s when idle; enqueueing can share the caller's
  transaction.

## Consequences

- No extra service; enqueue is transactional with domain writes (no lost or
  phantom jobs).
- Up to ~1 s pickup latency from polling; acceptable for batch work.
- Throughput is bounded by PostgreSQL; fine for tens of workers, revisit with
  `LISTEN/NOTIFY` or a broker if that changes.
- Correctness of concurrent claims is covered by integration tests against a
  real PostgreSQL 16 (`test_concurrent_claim_exactly_one_winner`).
