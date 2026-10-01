# ChatLedger

ChatLedger turns Slack exports into defensible, reproducible RSMF evidence
productions. Every message that does not reach the export is accounted for by a
reason code, and every run carries a manifest that lets you prove two runs are
identical, or explain why they are not.

## Quick start

Requires Docker with Compose v2.

```bash
git clone <repository-url> chatledger
cd chatledger
docker compose up
```

Then open <http://localhost:3000>. The API listens on <http://localhost:8000>
(`GET /health`, OpenAPI at `/docs`). Two workers start by default; scale them
with `docker compose up -d --scale worker=4`.

> If port 5432 is already in use on your machine, set `CHATLEDGER_DB_PORT=55432`
> in a `.env` file next to `docker-compose.yml`.

## Architecture

```mermaid
graph TD
    U[Browser] --> W["web — Next.js :3000"]
    W -->|"GET /health every 5 s"| A["api — FastAPI :8000"]
    W -->|"/api/v1/*"| A
    A --> C["chatledger_core — domain / usecase / infra"]
    WK["worker ×2 — job loop"] --> C
    CLI["chatledger-admin CLI"] --> C
    C --> DB[("PostgreSQL 16 — job, audit_event, worker_heartbeat")]
    A --> BS[("blobstore volume — /data/blobs")]
    WK --> BS
```

- **web**: a Next.js App Router app (TypeScript strict, Tailwind v4, TanStack
  Query). It uses a typed client generated from the API's OpenAPI schema.
- **api**: FastAPI. It applies Alembic migrations on start, returns a uniform
  error envelope `{"error": {"code", "message", "details"}}`, and echoes
  `X-Request-ID`.
- **worker**: a PostgreSQL job queue (`FOR UPDATE SKIP LOCKED`) with leases,
  retries and crash recovery. Each worker writes a heartbeat every 10 s.
- **chatledger_core**: the shared domain, use cases and adapters, with
  clean-architecture layering enforced by `import-linter`.
- **audit_event**: an append-only audit log, enforced by database triggers.

### Repository layout

| Path | Contents |
|---|---|
| `packages/core` | `chatledger_core`: config, domain, use cases, PostgreSQL adapters, Alembic migrations |
| `apps/api` | `chatledger_api`: FastAPI composition root and HTTP layer |
| `apps/worker` | `chatledger_worker`: job loop, handlers, `chatledger-admin` CLI |
| `apps/web` | Next.js web app |
| `docs/adr` | Architecture Decision Records |
| `scripts` | Coverage gate, git-SHA resolver, smoke test |

## Benchmarks

Measured with the synthetic export generator presets on a warm image cache.

| Preset | Messages | Conversations | Ingest time | Peak worker RSS | Throughput |
|---|---|---|---|---|---|
| `small` | pending (F04) | pending (F04) | pending (F04) | pending (F04) | pending (F04) |
| `medium` | pending (F04) | pending (F04) | pending (F04) | pending (F04) | pending (F04) |
| `large` | pending (F04) | pending (F04) | pending (F04) | pending (F04) | pending (F04) |

## Development

Local tooling: [uv](https://docs.astral.sh/uv/) (Python 3.12),
[pnpm](https://pnpm.io/) 9 (Node 22), GNU Make and Docker.

```bash
make install            # uv sync + pnpm install
docker compose up -d db # PostgreSQL 16 for integration tests (creates chatledger_test)
make check              # every quality gate CI runs
```

| Target | What it does |
|---|---|
| `make up` / `make down` | Build and start / stop the stack |
| `make check` | `lint` + `typecheck` + `test` + `web-test` + `web-build` |
| `make lint` | `ruff check`, `ruff format --check`, `import-linter`, `eslint` (`lint-py`, `lint-web`) |
| `make typecheck` | `mypy --strict` and `tsc --noEmit` (`typecheck-py`, `typecheck-web`) |
| `make test` | pytest (unit + integration against `TEST_DATABASE_URL`), then the per-segment coverage gate: `parsing`, `model` and `gates` each need ≥ 80% |
| `make web-test` | `vitest run` |
| `make web-build` | `next build` |
| `make migrate` | `alembic upgrade head` against `DATABASE_URL` |
| `make gen-api-types` | Regenerate `apps/web/src/lib/api/schema.d.ts` from the API's OpenAPI schema |
| `make smoke` | Boot the stack, wait for health, check the web shell and run a `noop` job |

Configuration is read only by `chatledger_core/config.py`; every setting and
its default is listed in [`.env.example`](.env.example). The Python tests read
[`.env.test`](.env.test). Variables already exported take precedence.

Operator CLI (inside the worker container):

```bash
docker compose exec worker chatledger-admin enqueue-noop --fail-times 1
docker compose exec worker chatledger-admin job-status <job-id>
```

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-postgres-as-job-queue.md) | PostgreSQL as the job queue |
| [0002](docs/adr/0002-content-addressed-blob-storage.md) | Content-addressed blob storage |
| [0003](docs/adr/0003-deterministic-message-ids.md) | Deterministic message IDs |
| [0004](docs/adr/0004-streaming-json-parsing.md) | Streaming JSON parsing |
| [0005](docs/adr/0005-reason-code-accounting.md) | Reason-code accounting |
| [0006](docs/adr/0006-clean-architecture-layering.md) | Clean-architecture layering |
| [0007](docs/adr/0007-sync-sqlalchemy-psycopg3.md) | Synchronous SQLAlchemy 2 with psycopg 3 |
