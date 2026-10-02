# Spec: Project Foundation

**Complexity:** medium

## 1. Technical Overview

**What.** F01 bootstraps the ChatLedger monorepo and every cross-cutting building block that later features use without naming it in their Consumes blocks:
- A uv-managed Python workspace (`packages/core`, `apps/api`, `apps/worker`) and a pnpm-managed Next.js app (`apps/web`).
- A Docker Compose stack of 4 services plus a content-addressed blob volume.
- PostgreSQL 16 with SQLAlchemy 2 and Alembic migrations applied on API start.
- A PostgreSQL job queue (`FOR UPDATE SKIP LOCKED`) with a complete worker runtime.
- An append-only audit log enforced by the database.
- A uniform HTTP error envelope.
- The web app shell with its shared state components.
- A Makefile of quality gates that CI invokes verbatim.
- The README and initial ADRs.

**Why.** Every later feature depends on these pieces:
- The queue is used by F03 (generation jobs), F04 (work units), F11 (export jobs) and F12 (diff jobs).
- The audit log is used by F02 onwards.
- The error envelope, settings module, DB session and app shell are used by every API and UI feature.

Building them once, with the layering rules in place, prevents drift. It also gives technical reviewers a concrete architecture to evaluate from the first commit. Because F01 is the only Foundation feature, its conventions (folder layout, test fixtures, seeding, config, mocks, gates) become the project's conventions.

**Scope.**

**Included:**
- Monorepo layout and workspace tooling: uv workspace with a single `uv.lock`, a pnpm project, and a root `Makefile`.
- `docker-compose.yml` services:
  - `db` (postgres:16).
  - `api` (:8000, runs `alembic upgrade head` before `uvicorn`).
  - `worker` (2 replicas by default, scalable with `--scale worker=N`).
  - `web` (:3000).
  - Named volumes `blobstore` (mounted at `/data/blobs` in `api` and `worker`) and `pgdata`.
- Git SHA resolution at image build time, overridable by the `GIT_SHA` build arg, and exposed to the API and worker.
- `packages/core`:
  - `config.py` (the only env reader).
  - Shared domain errors.
  - `JobQueue` and `AuditLog` ports with PostgreSQL adapters.
  - DB engine and session factory.
  - Alembic environment and migration `0001_foundation` (tables `job`, `audit_event`, `worker_heartbeat`; append-only trigger).
  - Empty bounded-context packages `parsing`, `model`, `gates` that later features fill.
- API: `GET /health`, the `/api/v1` router mount point, the global error envelope handlers, CORS for the web origin, and the OpenAPI schema.
- Worker:
  - Job loop with a handler registry keyed by job kind.
  - Lease renewal and expired-lease requeue.
  - Retry up to `max_attempts`.
  - Heartbeat upsert every 10 s.
  - Graceful SIGTERM shutdown.
  - A built-in `noop` handler with `fail_times` and `sleep_seconds` options.
- `chatledger-admin` CLI in the worker app: `enqueue-noop`, `job-status`.
- Structured JSON logging (structlog) in the API and worker.
- Web:
  - Root layout with left nav (Matters, Reason Codes) and a header slot for the current matter.
  - Design tokens (CSS variables) and IBM Plex fonts.
  - Radix-based Dialog, Tooltip and Toast primitives.
  - Shared `Skeleton`, `EmptyState` and `ErrorBanner` components.
  - API status banner driven by polling `/health` every 5 s.
  - Typed API client generated from OpenAPI, with TanStack Query provider.
  - Routes `/` (redirect), `/matters` (empty state) and `/reason-codes` (placeholder).
- Quality gates:
  - `make check` aggregates `lint`, `typecheck`, `test`, `web-test` and `web-build`.
  - A per-package coverage gate script (≥ 80% for each of `parsing`, `model`, `gates`).
- GitHub Actions workflow `ci.yml` (push + pull_request) calling the Makefile targets, with a postgres:16 service container.
- README (3-command quick start, architecture diagram, benchmark table, ADR index) and at least 5 ADRs in `docs/adr/`.

**Excluded (owned by later features):**
- Matter/collection tables and the "New matter" action (F02). F01 renders the button and empty state statically; F02 binds them to data.
- Reason-code catalogue content (F07). F01 renders the route with a placeholder.
- Any domain job kind other than `noop`.
- Benchmark numbers. The README table ships with "pending" rows that F04 fills.

**Input contracts (Consumes):** none (root feature).

**Output contracts (Provides — infrastructure, implicitly consumed by all later features):**
- `JobQueue` port: enqueue, claim, renew_lease, complete, fail, requeue_expired, get. Plus the worker handler registry for registering new job kinds.
- `AuditLog` port: record, list_for_entity.
- `Settings` object, DB `session_scope()` and `DomainError` hierarchy mapped to the HTTP error envelope.
- Web app shell, layout slots and shared UI state components, plus the typed `apiClient`.

## 2. Architecture Impact

**Affected components (all new):**
- `pyproject.toml`, `uv.lock`, `Makefile`, `docker-compose.yml`, `.env.example`, `.env.test`, `.github/workflows/ci.yml`, `scripts/check_coverage.py`
- `packages/core/chatledger_core/**`
- `apps/api/chatledger_api/**`, `apps/api/Dockerfile`
- `apps/worker/chatledger_worker/**`, `apps/worker/Dockerfile`
- `apps/web/**`, `apps/web/Dockerfile`
- `README.md`, `docs/adr/*.md`, `tests/fixtures/foundation/*`

```mermaid
graph TD
    U[Browser] --> W["web (Next.js :3000)"]
    W -->|"GET /health every 5s"| A["api (FastAPI :8000)"]
    W -->|"/api/v1/* (later features)"| A
    A --> C["chatledger_core (domain / usecase / infra)"]
    WK["worker x2 (job loop)"] --> C
    CLI["chatledger-admin CLI"] --> C
    C --> DB[("PostgreSQL 16: job, audit_event, worker_heartbeat")]
    A --> BS[("blobstore volume /data/blobs")]
    WK --> BS
    GS["git-sha build stage"] -.->|"/app/GIT_SHA"| A
    GS -.-> WK
    CI["GitHub Actions ci.yml"] -->|"make lint typecheck test web-test web-build"| MK[Makefile]
```

**Layering (Python adaptation of the repo `clean-arch` skill):**

```mermaid
graph TD
    R["composition roots: chatledger_api/main.py, chatledger_worker/main.py"] --> I["chatledger_core/infra (db, queue, audit, logging)"]
    R --> UC["chatledger_core/usecase"]
    I --> UC
    I --> D["chatledger_core/domain (_shared, jobs, audit)"]
    UC --> D
    CFG["chatledger_core/config.py (only env reader)"] --> R
```

Rules:
- `domain` imports nothing from `usecase`, `infra` or `config`.
- `usecase` imports only `domain`.
- `infra` implements ports declared in `domain`.
- Concrete adapters are instantiated only in the composition roots.
- These rules are enforced by `import-linter` contracts run inside `make lint`.

## 3. Technical Decisions

| Decision | Chosen Approach | Alternative Considered | Trade-off |
|----------|----------------|----------------------|-----------|
| Code organisation | Python adaptation of the repo's clean-arch skill: `packages/core/chatledger_core/{domain,usecase,infra}`, thin API/worker composition roots, `config.py` as the single env reader, enforced with `import-linter` | Flat FastAPI routers/services layout | More files and indirection up front, in exchange for a clear dependency rule that reviewers can verify and that keeps parsing and gate logic testable without a DB |
| Package management | uv workspace (one lock for core/api/worker) + pnpm for web, root Makefile as the single entry point | Poetry per app + npm | Requires uv and pnpm locally (both single-binary installs); CI and developers run identical commands |
| DB access style | SQLAlchemy 2 **sync** engine with the psycopg 3 driver in both API (FastAPI `def` routes, threadpool) and worker | Async SQLAlchemy + asyncpg | Lower peak concurrency in the API, which a single-user app doesn't need. Gains simpler transactions, the same code path in API and worker, and native `COPY` support needed by F04 |
| Job queue | Postgres `job` table claimed with `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1` ordered by `(priority, created_at)`, 60 s leases renewed every 20 s, expired-lease sweep every 15 s by every worker, max 3 attempts with linear backoff `5 s × attempts` | `LISTEN/NOTIFY` push, or Celery/Redis | Polling (1 s idle interval) adds up to 1 s pickup latency; no extra infrastructure and transactional enqueue alongside domain writes |
| Audit immutability | `BEFORE UPDATE OR DELETE` row trigger + `BEFORE TRUNCATE` statement trigger raising `audit_event is append-only` | Application-level discipline or revoked grants | The trigger also blocks maintenance edits, which is intended; works for the single DB role used by the PoC |
| Git SHA in images | Multi-stage build: a `git-sha` stage copies `.git` and runs `git rev-parse HEAD` into `/GIT_SHA`; the final image copies only that file. A `GIT_SHA` build arg overrides it; falls back to `unknown` when `.git` is absent | Require `GIT_SHA=$(git rev-parse HEAD) docker compose up` | `.git` enters the build context (larger context upload); plain `docker compose up` on a clean clone reports the real SHA as the PRD requires |
| Coverage gate | `pytest --cov` writes `coverage.json`; `scripts/check_coverage.py` aggregates statements per **path segment** (`parsing`, `model`, `gates`) across `packages/` and `apps/`, failing if any segment with > 0 statements is < 80% | Global `--cov-fail-under=80` | Works regardless of which layer later features place those modules in, and a well-tested package cannot mask an under-tested one; needs a small custom script |
| Web data access | Browser calls FastAPI directly at `NEXT_PUBLIC_API_URL` with CORS, via an `openapi-typescript`-generated typed client and TanStack Query v5 | Next.js route-handler proxy | CORS configuration needed; avoids double-hop for 2 GB uploads (F02) and gives polling (`refetchInterval`) for free |
| UI foundation | Tailwind v4 + custom CSS-variable design tokens ("evidence ledger": paper-grey surfaces, ink text, single oxblood accent, IBM Plex Sans/Mono, 4 px grid, hairline rules) + headless Radix primitives | shadcn/ui defaults | More initial design work; avoids the template look penalised by the project's `frontend-ui-design` evaluation criteria |

**Assumptions** (derived from the interview, PRD and greenfield defaults):
- **A1 – Toolchain versions:** Python 3.12, Node 22 LTS, pnpm 9, uv ≥ 0.4, Next.js 15 (App Router), React 19, Tailwind 4, TanStack Query 5, PostgreSQL 16, Docker Compose v2.
- **A2 – Error envelope:** every API error is `{ "error": { "code", "message", "details" } }`. The PRD's `{code, message}` (F04) lives under the `error` key.
- **A3 – Route layout:** `/health` stays at the root (Docker healthcheck, PRD wording). All domain routes mount under `/api/v1`.
- **A4 – Matters page in F01:** `/matters` renders the PRD empty state statically, and the "New matter" button opens nothing yet. F02 replaces the static source with data and wires the modal (Preparation Pattern: F01 must not depend on F02).
- **A5 – Benchmark table:** the README table has rows for the `small`, `medium` and `large` presets with values `pending (F04)`.
- **A6 – Test conventions (become project conventions):**
  - Per-package `tests/{unit,integration}`, with shared static fixtures in root `tests/fixtures/<feature-slug>/`.
  - DB state comes from pytest fixtures plus factory functions in `packages/core/tests/factories.py`; no SQL seed files.
  - Integration tests use the real PG16 at `TEST_DATABASE_URL`, run migrations once per session, and wrap each test in a rolled-back transaction (queue concurrency tests use separate committed connections and truncate `job` afterwards).
  - Python tests read `.env.test`.
  - Web tests use Vitest + Testing Library with MSW handlers in `apps/web/tests/mocks/`.
- **A7 – Job queue defaults:** lease 60 s, renew every 20 s, sweep every 15 s, idle poll 1 s and max attempts 3 are all overridable via settings. `.env.test` lowers lease and sweep to 5 s and 2 s for fast integration tests.
- **A8 – Worker concurrency:** each worker process handles one job at a time. Parallelism comes from replicas (`deploy.replicas: 2`).
- **A9 – Heartbeat liveness:** a worker counts as active when its heartbeat is less than 30 s old. `/health` reports that count, and F08 reuses it.
- **A10 – API status banner timing:** the banner appears after the first failed `/health` poll (5 s interval, 3 s timeout), so within ≤ 10 s of the API going down. It clears on the next successful poll.

## 4. Component Overview

**Root / tooling:**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `pyproject.toml` | New | uv workspace root | Declares members `packages/core`, `apps/api`, `apps/worker`; ruff, mypy (strict), pytest, coverage and import-linter config |
| `Makefile` | New | Quality-gate and dev entry point | Targets `up`, `down`, `check`, `lint` (`lint-py`, `lint-web`), `typecheck` (`typecheck-py`, `typecheck-web`), `test`, `web-test`, `web-build`, `migrate`, `gen-api-types` |
| `scripts/check_coverage.py` | New | Per-segment coverage gate | Reads `coverage.json`; aggregates covered/total statements per path segment `parsing`/`model`/`gates`; exits 1 with `Coverage gate failed: <segment> <pct>% < 80%` |
| `docker-compose.yml` | New | Local stack | Services `db`, `api`, `worker` (replicas 2), `web`; volumes `pgdata`, `blobstore`; healthchecks; `depends_on` with `service_healthy` |
| `.env.example`, `.env.test` | New | Configuration templates | Every setting from §5 Configuration with defaults; test overrides (short leases, `TEST_DATABASE_URL`) |
| `.dockerignore` | New | Build context hygiene | Excludes `node_modules`, `.venv`, caches; keeps `.git` for the `git-sha` stage |
| `.github/workflows/ci.yml` | New | CI | Triggers on `push`, `pull_request`; job `python` (postgres:16 service, `uv sync`, `make lint-py typecheck-py test`); job `web` (`pnpm install --frozen-lockfile`, `make lint-web typecheck-web web-test web-build`) |
| `README.md` | New | Project entry doc | Quick start (3 commands), architecture Mermaid diagram, benchmark table, ADR index, make targets |
| `docs/adr/0001-postgres-as-job-queue.md` … `0007-*.md` | New | ADRs | 0001 Postgres queue, 0002 content-addressed blob storage, 0003 deterministic message IDs, 0004 streaming JSON parsing, 0005 reason-code accounting, 0006 clean-architecture layering, 0007 sync SQLAlchemy + psycopg3. Format: Status / Context / Decision / Consequences |

**Backend — `packages/core/chatledger_core`:**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `config.py` | New | Settings | `Settings` (pydantic-settings) with every env var; `get_settings()` cached; only module reading the environment |
| `domain/_shared/errors.py` | New | Error hierarchy | `DomainError(code, message, details)` base; `NotFoundError` (404), `ConflictError` (409), `ValidationFailedError` (422), `UnavailableError` (503) |
| `domain/_shared/clock.py` | New | Time port | `Clock` protocol + `SystemClock` (UTC), injectable for tests |
| `domain/jobs/job.py` | New | Job entity | `Job` dataclass, `JobState` enum (`queued`, `leased`, `done`, `failed`) |
| `domain/jobs/queue.py` | New | Queue port | `JobQueue` protocol: `enqueue`, `claim`, `renew_lease`, `complete`, `fail`, `requeue_expired`, `get` |
| `domain/audit/audit_event.py` | New | Audit entity + port | `AuditEvent` dataclass; `AuditLog` protocol: `record`, `list_for_entity` |
| `infra/db/engine.py` | New | DB wiring | Engine factory (psycopg3), `session_scope()` context manager, `ping()` for health |
| `infra/db/tables.py` | New | SQLAlchemy Core tables | `job`, `audit_event`, `worker_heartbeat` table definitions (metadata used by Alembic) |
| `infra/queue/pg_job_queue.py` | New | Queue adapter | SKIP LOCKED claim, lease renewal, retry/backoff, expired-lease sweep |
| `infra/audit/pg_audit_log.py` | New | Audit adapter | Inserts and reads `audit_event` |
| `infra/heartbeat/pg_heartbeat.py` | New | Heartbeat adapter | Upsert heartbeat; count active workers (< 30 s) |
| `infra/logging.py` | New | Logging | structlog JSON renderer, `bind_context()` helper |
| `infra/git_sha.py` | New | Build metadata | Reads `GIT_SHA` env or `/app/GIT_SHA` file; returns 40-hex or `unknown` |
| `migrations/env.py`, `migrations/versions/0001_foundation.py` | New | Alembic | Creates the 3 tables, indexes and append-only triggers |
| `parsing/__init__.py`, `model/__init__.py`, `gates/__init__.py` | New | Coverage-gated placeholders | Empty packages filled by F04/F05/F07 |
| `tests/factories.py` | New | Test factories | `make_job(...)`, `make_audit_event(...)` builders |

**Backend — `apps/api/chatledger_api`:**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `main.py` | New | Composition root | Builds `FastAPI` app, wires adapters, mounts `/health` and `/api/v1` router, CORS, error handlers |
| `http/errors.py` | New | Error envelope | Handlers for `DomainError`, `RequestValidationError` (422 `VALIDATION_ERROR`), `StarletteHTTPException` (404 `NOT_FOUND`, 405 `METHOD_NOT_ALLOWED`), unhandled (500 `INTERNAL_ERROR`, no stack trace in body) |
| `http/routes/health.py` | New | Health endpoint | DB ping, migration revision, blob store writability, active workers, git SHA |
| `http/routes/v1.py` | New | v1 router | Empty `APIRouter(prefix="/api/v1")` later features include into |
| `entrypoint.sh` | New | Container start | `alembic upgrade head` then `uvicorn chatledger_api.main:app --host 0.0.0.0 --port 8000` |
| `apps/api/Dockerfile` | New | Image | Stages `git-sha`, `deps` (uv sync --frozen), `runtime` (python:3.12-slim) |

**Backend — `apps/worker/chatledger_worker`:**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `main.py` | New | Composition root | Wires queue, heartbeat, registry; starts loop; installs SIGTERM/SIGINT handlers |
| `loop.py` | New | Job loop | Claim → dispatch to handler → complete/fail; lease-renewal thread; sweep every 15 s; idle poll 1 s; stop flag |
| `registry.py` | New | Handler registry | `register(kind, handler)`; unknown kind → job fails with `UNKNOWN_JOB_KIND` |
| `handlers/noop.py` | New | Built-in handler | Payload `{fail_times: int=0, sleep_seconds: float=0}`; raises `NoopFailure` while `attempts <= fail_times` |
| `heartbeat.py` | New | Heartbeat thread | Upserts `worker_heartbeat` every 10 s with worker_id `<hostname>-<pid>` |
| `admin_cli.py` | New | `chatledger-admin` | `enqueue-noop [--fail-times N] [--sleep-seconds S] [--priority P]` prints job UUID; `job-status <id>` prints job JSON |
| `apps/worker/Dockerfile` | New | Image | Same stages as API; entrypoint `chatledger-worker` |

**Frontend — `apps/web`:**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `package.json`, `pnpm-lock.yaml`, `tsconfig.json` (strict), `eslint.config.mjs`, `vitest.config.ts` | New | Project config | Scripts `dev`, `build`, `lint`, `typecheck`, `test`, `gen:api` |
| `src/app/layout.tsx` | New | Root layout | Fonts, `Providers`, `AppShell` |
| `src/app/page.tsx` | New | Root route | Redirects to `/matters` |
| `src/app/matters/page.tsx` | New | Matters route | Static `EmptyState` "No matters yet. Create one to start." + "New matter" primary button (wired by F02) |
| `src/app/reason-codes/page.tsx` | New | Reason Codes route | Placeholder `EmptyState` "Reason codes will be listed here once quality gates are available." |
| `src/app/globals.css` | New | Design tokens | CSS variables (color, type scale, spacing, radius, rules), Tailwind v4 `@theme` mapping |
| `src/components/shell/AppShell.tsx`, `SideNav.tsx`, `HeaderBar.tsx` | New | Shell | Left nav with active state, header with `currentMatter` slot (empty in F01), main content region |
| `src/components/state/EmptyState.tsx`, `Skeleton.tsx`, `ErrorBanner.tsx` | New | Shared states | Reusable title/description/action empty state; skeleton rows; dismissible/persistent banner |
| `src/components/ui/Dialog.tsx`, `Tooltip.tsx`, `Toast.tsx` | New | Radix wrappers | Token-styled accessible primitives; `useToast()` |
| `src/components/system/ApiStatusBanner.tsx` | New | API status | Polls `/health` every 5 s (3 s timeout); shows persistent top banner on failure; clears on success |
| `src/lib/api/client.ts`, `src/lib/api/schema.d.ts` | New | Typed client | `openapi-fetch` client over generated types; base URL from `NEXT_PUBLIC_API_URL`; parses error envelope into `ApiError` |
| `src/lib/query/Providers.tsx` | New | Query provider | TanStack `QueryClient` defaults (retry 1, no refetch on focus) + Toast provider |
| `tests/mocks/handlers.ts`, `tests/setup.ts` | New | MSW | Default `/health` 200 handler; per-test overrides |
| `apps/web/Dockerfile` | New | Image | `node:22-alpine`, pnpm, `next build` standalone output |

**Database:**

| Migration File | Tables Affected | Operation | Notes |
|----------------|-----------------|-----------|-------|
| `packages/core/chatledger_core/migrations/versions/0001_foundation.py` | `job`, `audit_event`, `worker_heartbeat` | CREATE | Includes partial indexes, CHECK constraints, `audit_event_append_only()` trigger function and 2 triggers |

## 5. API Contracts

### Endpoint: Health

- **Method:** GET
- **Path:** `/health`
- **Authentication:** none (single-user local app)

**Request:** no parameters.

**Response (200 when DB reachable and migrations at head; 503 otherwise):**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | `ok` when every check passes; `degraded` otherwise |
| `checks.database` | `string` | `ok` \| `unavailable` |
| `checks.migrations` | `string` | `ok` (DB revision equals Alembic head) \| `pending` \| `unknown` |
| `checks.blob_store` | `string` | `ok` (`BLOB_ROOT` exists and is writable) \| `unavailable` |
| `migration_revision` | `string \| null` | Current DB revision, e.g. `0001_foundation` |
| `git_sha` | `string` | 40-char lowercase hex or `unknown` |
| `active_workers` | `integer` | Workers with heartbeat < 30 s old (0 when DB unavailable) |
| `version` | `string` | Package version, e.g. `0.1.0` |

**Response Example (200):**
```json
{
  "status": "ok",
  "checks": { "database": "ok", "migrations": "ok", "blob_store": "ok" },
  "migration_revision": "0001_foundation",
  "git_sha": "3f9c2a7d1e0b4c8a9f6e5d4c3b2a19081726354a",
  "active_workers": 2,
  "version": "0.1.0"
}
```

**Response Example (503):**
```json
{
  "status": "degraded",
  "checks": { "database": "unavailable", "migrations": "unknown", "blob_store": "ok" },
  "migration_revision": null,
  "git_sha": "3f9c2a7d1e0b4c8a9f6e5d4c3b2a19081726354a",
  "active_workers": 0,
  "version": "0.1.0"
}
```

`blob_store: unavailable` alone yields `status: degraded` but HTTP 200, so the container healthcheck doesn't block on a volume permission issue. A DB or migration failure yields 503.

### Error envelope (all endpoints, all later features)

| Field | Type | Description |
|-------|------|-------------|
| `error.code` | `string` | UPPER_SNAKE stable code |
| `error.message` | `string` | Human-readable sentence, safe to show in the UI |
| `error.details` | `object` | Optional structured context (e.g. field errors); `{}` when none |

**Example (unknown route):**
```json
{ "error": { "code": "NOT_FOUND", "message": "Route GET /api/v1/nope not found.", "details": {} } }
```

**Example (validation):**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": { "fields": [ { "loc": ["body", "name"], "msg": "String should have at least 3 characters" } ] }
  }
}
```

**Error Codes (foundation-level):**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Unknown route or `NotFoundError` |
| `METHOD_NOT_ALLOWED` | 405 | Route exists with a different method |
| `VALIDATION_ERROR` | 422 | Pydantic request validation failure |
| `CONFLICT` | 409 | Default code for `ConflictError` subclasses without their own code |
| `SERVICE_UNAVAILABLE` | 503 | `UnavailableError` (e.g. DB down) |
| `INTERNAL_ERROR` | 500 | Unhandled exception; message "Unexpected server error. See API logs (request_id=<id>)." No stack trace in body |

Every response carries an `X-Request-ID` header (incoming value echoed, or a generated UUID4), which is also bound into log lines.

**CORS:** allow origins from `CORS_ORIGINS` (default `http://localhost:3000`), methods `GET, POST, PUT, PATCH, DELETE, OPTIONS`, headers `*`, expose `X-Request-ID`.

### CLI: `chatledger-admin` (inside the worker image)

| Command | Arguments | Output | Exit code |
|---|---|---|---|
| `enqueue-noop` | `--fail-times N` (int ≥ 0, default 0), `--sleep-seconds S` (float 0–300, default 0), `--priority P` (int 0–1000, default 100) | Job UUID on stdout | 0; 2 on invalid argument |
| `job-status <job_id>` | job UUID | JSON `{id, kind, state, attempts, max_attempts, last_error, created_at, finished_at}` | 0; 1 with `Job <id> not found` on stderr |

### Configuration (`Settings`, read only in `config.py`)

| Env var | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://chatledger:chatledger@db:5432/chatledger` | api, worker, CLI |
| `TEST_DATABASE_URL` | `postgresql+psycopg://chatledger:chatledger@localhost:5432/chatledger_test` | tests |
| `BLOB_ROOT` | `/data/blobs` | api, worker |
| `GIT_SHA` | (from build file, else `unknown`) | api, worker |
| `LOG_LEVEL` | `INFO` | api, worker |
| `CORS_ORIGINS` | `http://localhost:3000` | api |
| `JOB_LEASE_SECONDS` | `60` | worker |
| `JOB_LEASE_RENEW_SECONDS` | `20` | worker |
| `JOB_SWEEP_INTERVAL_SECONDS` | `15` | worker |
| `JOB_POLL_INTERVAL_SECONDS` | `1.0` | worker |
| `JOB_MAX_ATTEMPTS` | `3` | queue |
| `JOB_RETRY_BACKOFF_SECONDS` | `5` | queue |
| `HEARTBEAT_INTERVAL_SECONDS` | `10` | worker |
| `WORKER_ACTIVE_WINDOW_SECONDS` | `30` | api health |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | web |

### Queue port semantics (`JobQueue`, consumed by F03, F04, F11, F12)

| Operation | Behaviour |
|---|---|
| `enqueue(kind, payload, *, priority=100, group_key=None, max_attempts=None)` | Inserts `queued` job with `run_after=now()`; returns `Job`. Can participate in the caller's transaction |
| `claim(worker_id)` | One transaction: `SELECT … WHERE state='queued' AND run_after <= now() ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT 1`; sets `state='leased'`, `lease_owner`, `lease_expires_at=now()+lease`, `attempts=attempts+1`, `started_at` if null. Returns `Job` or `None` |
| `renew_lease(job_id, worker_id)` | Extends `lease_expires_at` only if `lease_owner=worker_id` and `state='leased'`; returns `False` if the lease was lost (handler must abort) |
| `complete(job_id, worker_id)` | `state='done'`, `finished_at=now()`, clears lease; no-op returning `False` if lease lost |
| `fail(job_id, worker_id, error)` | Stores `last_error` (≤ 4,000 chars). If `attempts < max_attempts`: `state='queued'`, `run_after=now()+backoff×attempts`. Else `state='failed'`, `finished_at=now()` |
| `requeue_expired()` | For `state='leased' AND lease_expires_at < now()`: same retry/fail rule as `fail` with `last_error='lease expired (owner <worker_id>)'`. Returns count |
| `get(job_id)` | Returns `Job` or raises `NotFoundError` |

## 6. Data Model

**Table: `job`**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `uuid` | No | `gen_random_uuid()` | Primary key |
| `kind` | `varchar(64)` | No | - | Handler key, e.g. `noop`, `unit`, `generate`, `export` |
| `payload` | `jsonb` | No | `'{}'` | Handler-specific input |
| `state` | `varchar(16)` | No | `'queued'` | `queued` \| `leased` \| `done` \| `failed` |
| `priority` | `smallint` | No | `100` | Lower is claimed first |
| `group_key` | `varchar(128)` | Yes | - | Optional grouping (e.g. `run:<uuid>`) for later progress/cancel queries |
| `attempts` | `integer` | No | `0` | Incremented on each claim |
| `max_attempts` | `integer` | No | `3` | Retry budget |
| `lease_owner` | `varchar(128)` | Yes | - | `<hostname>-<pid>` of the leasing worker |
| `lease_expires_at` | `timestamptz` | Yes | - | Lease deadline |
| `run_after` | `timestamptz` | No | `now()` | Earliest claim time (backoff) |
| `last_error` | `text` | Yes | - | Last failure message (≤ 4,000 chars) |
| `created_at` | `timestamptz` | No | `now()` | |
| `started_at` | `timestamptz` | Yes | - | First claim time |
| `finished_at` | `timestamptz` | Yes | - | Terminal time |
| `updated_at` | `timestamptz` | No | `now()` | Updated on every state change |

**Indexes:**

| Index Name | Columns | Type | Purpose |
|------------|---------|------|---------|
| `ix_job_claimable` | `(priority, created_at)` WHERE `state = 'queued'` | btree partial | Fast claim ordering |
| `ix_job_leased_expiry` | `lease_expires_at` WHERE `state = 'leased'` | btree partial | Expired-lease sweep |
| `ix_job_group_state` | `(group_key, state)` WHERE `group_key IS NOT NULL` | btree partial | Per-run progress/cancel |

**Constraints:**

| Constraint | Type | Definition | Purpose |
|------------|------|------------|---------|
| `pk_job` | PRIMARY KEY | `id` | Identity |
| `ck_job_state` | CHECK | `state IN ('queued','leased','done','failed')` | Valid states |
| `ck_job_attempts` | CHECK | `attempts >= 0 AND max_attempts >= 1` | Sane counters |
| `ck_job_lease` | CHECK | `state <> 'leased' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)` | Leased jobs always have an owner and deadline |

**Table: `audit_event`**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | `bigint` (identity) | No | generated always | Monotonic order |
| `occurred_at` | `timestamptz` | No | `now()` | UTC timestamp |
| `action` | `varchar(64)` | No | - | Dotted action, e.g. `matter.created` |
| `entity_type` | `varchar(64)` | No | - | e.g. `matter`, `run` |
| `entity_id` | `varchar(128)` | No | - | Entity identifier as text |
| `details` | `jsonb` | No | `'{}'` | Action-specific context |

**Indexes:** `ix_audit_entity` on `(entity_type, entity_id, id)` btree; `ix_audit_occurred_at` on `occurred_at` btree.

**Constraints / triggers:** `pk_audit_event` PRIMARY KEY `id`; `ck_audit_action_format` CHECK `action ~ '^[a-z_]+(\.[a-z_]+)+$'`; trigger `trg_audit_event_no_update_delete` BEFORE UPDATE OR DELETE FOR EACH ROW and `trg_audit_event_no_truncate` BEFORE TRUNCATE FOR EACH STATEMENT, both executing `audit_event_append_only()` which raises `'audit_event is append-only'` with SQLSTATE `55000` (object_not_in_prerequisite_state).

**Table: `worker_heartbeat`**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `worker_id` | `varchar(128)` | No | - | Primary key, `<hostname>-<pid>` |
| `hostname` | `varchar(255)` | No | - | Container hostname |
| `pid` | `integer` | No | - | Process ID |
| `git_sha` | `varchar(40)` | No | - | Worker build SHA or `unknown` |
| `started_at` | `timestamptz` | No | `now()` | Process start |
| `last_seen_at` | `timestamptz` | No | `now()` | Last heartbeat |
| `current_job_id` | `uuid` | Yes | - | Job being processed, if any |

**Indexes:** `ix_worker_heartbeat_last_seen` on `last_seen_at` btree.

**Migration Example:**
```sql
CREATE TABLE job (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    state VARCHAR(16) NOT NULL DEFAULT 'queued'
        CONSTRAINT ck_job_state CHECK (state IN ('queued','leased','done','failed')),
    priority SMALLINT NOT NULL DEFAULT 100,
    group_key VARCHAR(128),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    lease_owner VARCHAR(128),
    lease_expires_at TIMESTAMPTZ,
    run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_job_attempts CHECK (attempts >= 0 AND max_attempts >= 1),
    CONSTRAINT ck_job_lease CHECK (state <> 'leased' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE INDEX ix_job_claimable ON job (priority, created_at) WHERE state = 'queued';
CREATE INDEX ix_job_leased_expiry ON job (lease_expires_at) WHERE state = 'leased';
CREATE INDEX ix_job_group_state ON job (group_key, state) WHERE group_key IS NOT NULL;

CREATE TABLE audit_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    action VARCHAR(64) NOT NULL CONSTRAINT ck_audit_action_format CHECK (action ~ '^[a-z_]+(\.[a-z_]+)+$'),
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_audit_entity ON audit_event (entity_type, entity_id, id);
CREATE INDEX ix_audit_occurred_at ON audit_event (occurred_at);

CREATE FUNCTION audit_event_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_event is append-only' USING ERRCODE = '55000';
END $$;
CREATE TRIGGER trg_audit_event_no_update_delete BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
CREATE TRIGGER trg_audit_event_no_truncate BEFORE TRUNCATE ON audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION audit_event_append_only();

CREATE TABLE worker_heartbeat (
    worker_id VARCHAR(128) PRIMARY KEY,
    hostname VARCHAR(255) NOT NULL,
    pid INTEGER NOT NULL,
    git_sha VARCHAR(40) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_job_id UUID
);
CREATE INDEX ix_worker_heartbeat_last_seen ON worker_heartbeat (last_seen_at);
```

## 7. Testing Strategy

**Test File Structure:**

| Test File | Test Type | Target | Coverage Goal |
|-----------|-----------|--------|---------------|
| `packages/core/tests/unit/test_settings.py` | Unit | `config.Settings` | 95% |
| `packages/core/tests/unit/test_git_sha.py` | Unit | `infra/git_sha.py` | 100% |
| `packages/core/tests/integration/test_migrations.py` | Integration | Alembic `0001_foundation` | upgrade/downgrade round trip |
| `packages/core/tests/integration/test_pg_job_queue.py` | Integration | `PgJobQueue` | 95% |
| `packages/core/tests/integration/test_pg_audit_log.py` | Integration | `PgAuditLog` + triggers | 95% |
| `packages/core/tests/integration/test_pg_heartbeat.py` | Integration | `PgHeartbeat` | 90% |
| `apps/api/tests/integration/test_health.py` | Integration | `GET /health` | 100% of route |
| `apps/api/tests/unit/test_error_envelope.py` | Unit | `http/errors.py` | 100% |
| `apps/worker/tests/integration/test_loop.py` | Integration | `loop.py`, `registry.py`, `handlers/noop.py` | 90% |
| `apps/worker/tests/unit/test_admin_cli.py` | Unit | `admin_cli.py` (argument parsing, output) | 90% |
| `scripts/tests/test_check_coverage.py` | Unit | `check_coverage.py` | 100% |
| `tests/architecture/test_import_rules.py` | Unit | import-linter contracts | n/a |
| `apps/web/src/components/system/ApiStatusBanner.test.tsx` | Component | Banner behaviour with MSW | 100% |
| `apps/web/src/components/shell/AppShell.test.tsx` | Component | Nav, active state, header slot | 90% |
| `apps/web/src/app/matters/page.test.tsx` | Component | Empty state copy and button | 100% |
| `apps/web/src/lib/api/client.test.ts` | Unit | Error envelope parsing into `ApiError` | 100% |

**`test_pg_job_queue.py`:**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_enqueue_creates_queued_job` | Enqueue noop | state `queued`, attempts 0, run_after ≤ now |
| `test_claim_orders_by_priority_then_created_at` | 3 jobs, priorities 100/10/100 | claims return priority-10 job first, then older 100 |
| `test_concurrent_claim_exactly_one_winner` | 2 connections in threads claim 1 job via barrier | exactly one returns the job, other returns `None` |
| `test_concurrent_claim_many_jobs_no_duplicates` | 8 threads × 50 jobs | every job claimed exactly once |
| `test_claim_skips_future_run_after` | job with run_after +10 s | `claim` returns `None` |
| `test_renew_lease_only_by_owner` | other worker renews | returns `False`, deadline unchanged |
| `test_fail_requeues_with_backoff` | attempts 1 of 3 | state `queued`, run_after ≈ now+5 s, last_error stored |
| `test_fail_final_attempt_marks_failed` | attempts 3 of 3 | state `failed`, finished_at set |
| `test_requeue_expired_leases` | lease deadline in the past | job back to `queued`, last_error mentions lease expiry |
| `test_requeue_expired_exhausted_marks_failed` | expired with attempts 3 | state `failed` |
| `test_complete_after_lost_lease_is_noop` | lease taken over | returns `False`, state unchanged |

**`test_pg_audit_log.py`:**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_record_returns_event_with_id` | Record `test.seeded` | id > 0, occurred_at UTC, details round-trip |
| `test_update_rejected_by_trigger` | Raw `UPDATE audit_event` | raises DB error SQLSTATE 55000, message `audit_event is append-only` |
| `test_delete_rejected_by_trigger` | Raw `DELETE` | same error |
| `test_truncate_rejected_by_trigger` | Raw `TRUNCATE` | same error |
| `test_invalid_action_format_rejected` | action `Bad Action` | CHECK violation |
| `test_list_for_entity_ordered` | 3 events | returned in id order |

**`test_health.py`:**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_health_ok` | Migrated DB | 200, `status=ok`, revision `0001_foundation`, git_sha matches setting |
| `test_health_db_unavailable` | Engine pointing to closed port | 503, `checks.database=unavailable` |
| `test_health_migrations_pending` | DB at base revision | 503, `checks.migrations=pending` |
| `test_health_active_workers_counts_recent_only` | heartbeats at -5 s and -45 s | `active_workers=1` |
| `test_health_blob_store_unwritable` | `BLOB_ROOT` read-only temp dir | 200, `status=degraded`, `checks.blob_store=unavailable` |

**`test_error_envelope.py`:**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_unknown_route_404_envelope` | GET `/api/v1/nope` | 404 `{error.code: NOT_FOUND}` |
| `test_validation_error_envelope` | test-only route with Pydantic body | 422 `VALIDATION_ERROR`, `details.fields` non-empty |
| `test_domain_error_mapping` | raise `ConflictError` subclass | 409 with its code |
| `test_unhandled_exception_hides_trace` | route raising `RuntimeError` | 500 `INTERNAL_ERROR`, no traceback text, `X-Request-ID` present |
| `test_request_id_echoed` | header supplied | same value returned |

**`test_loop.py`:**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_noop_job_completes` | loop runs one iteration | state `done`, attempts 1 |
| `test_noop_fail_times_retried_then_done` | `fail_times=1`, backoff 0 | attempts 2, state `done` |
| `test_noop_exhausts_attempts` | `fail_times=5` | state `failed`, attempts 3, last_error contains `NoopFailure` |
| `test_unknown_kind_fails_job` | kind `bogus` | state `failed`, last_error `UNKNOWN_JOB_KIND` |
| `test_lease_renewed_during_long_job` | sleep 3 s with lease 2 s / renew 0.5 s | job not re-claimed by second loop, ends `done` attempts 1 |
| `test_graceful_stop_finishes_current_job` | stop flag during sleep job | job `done`, loop exits, no new claims |
| `test_heartbeat_upserts` | heartbeat thread | row exists, `last_seen_at` advances |

**`test_check_coverage.py`:** `test_passes_when_all_segments_at_or_above_80`, `test_fails_naming_segment_below_80`, `test_segment_with_zero_statements_passes`, `test_segment_matching_is_by_path_component_not_substring` (e.g. `models/` is not `model/`).

**Frontend tests:**
- `ApiStatusBanner.test.tsx`: `renders_nothing_when_health_ok`; `shows_banner_after_failed_poll` (fake timers, MSW network error → banner text "API unavailable at http://localhost:8000. Check `docker compose ps`."); `clears_banner_when_health_recovers`.
- `AppShell.test.tsx`: `renders_nav_items_matters_and_reason_codes`; `marks_active_route`; `header_slot_renders_children`.
- `matters/page.test.tsx`: `shows_empty_state_copy`; `shows_new_matter_primary_button`.
- `client.test.ts`: `parses_error_envelope_into_ApiError`; `network_failure_raises_ApiUnavailableError`.

**E2E / smoke scenarios (scripted, run manually or in an optional CI job):**
- `scripts/smoke.sh`: from a clean clone, `docker compose up -d --wait`, then `curl /health` until 200 or 60 s timeout, `curl http://localhost:3000/matters` contains "No matters yet", then `docker compose exec worker chatledger-admin enqueue-noop` and poll `job-status` until `done`.
- Worker crash recovery: enqueue `noop --sleep-seconds 30`, `docker kill` the leasing worker, then assert the job reaches `done` with `attempts=2` within lease + 30 s.
