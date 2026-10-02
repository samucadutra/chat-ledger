# Implementation Plan: Project Foundation

**Prerequisites:**
- Docker Engine 24+ with Compose v2
- Python 3.12 and uv ≥ 0.4
- Node.js 22 LTS and pnpm 9
- GNU Make, git
- Environment variables as listed in spec §5 Configuration (templated in `.env.example` and `.env.test`)
- A local PostgreSQL 16 for integration tests (the compose `db` service exposed on port 5432 is sufficient)

### Stage 1: Repository and Tooling Skeleton

**1. Monorepo Layout** - Create the folder structure for `packages/core`, `apps/api`, `apps/worker`, `apps/web`, `scripts`, `tests/fixtures`, and `docs/adr`. Add the root git ignore and docker ignore files described in the spec.

**2. Python Workspace** - Set up the uv workspace with the core, api and worker members and a single lock file. Configure linting, strict type checking, test running, coverage and import-layering rules at the root, as listed in spec §3 and §4.

**3. Web Project Bootstrap** - Initialise the Next.js App Router project with TypeScript strict mode, Tailwind, ESLint, Vitest with Testing Library, and MSW. Add the package scripts the Makefile calls.

**4. Makefile and Coverage Gate Script** - Create the root Makefile with the dev, quality-gate and aggregate `check` targets. Add the per-segment coverage gate script so `make test` fails when any gated segment falls below 80%.

### Stage 2: Core Platform (Database, Queue, Audit)

**5. Settings and Shared Domain** - Implement the single settings module that reads the environment, the domain error hierarchy, the clock abstraction, and the build git-SHA reader. Add the empty `parsing`, `model` and `gates` placeholder packages.

**6. Database Wiring and Initial Migration** - Implement the engine and session factory, the table definitions and the Alembic environment. Write the `0001_foundation` migration that creates the job, audit and heartbeat tables with their indexes, constraints and append-only triggers.

**7. Job Queue Port and Postgres Adapter** - Define the queue port and implement the Postgres adapter: skip-locked claiming, lease renewal, retry with backoff, terminal failure and expired-lease requeue, following the semantics table in spec §5.

**8. Audit Log and Heartbeat Adapters** - Implement the audit log port and adapter for recording and listing events, and the heartbeat adapter for upserting liveness and counting active workers.

**9. Structured Logging and Test Factories** - Add the JSON logging setup used by the API and worker, and the shared test factories and database fixtures that later features will reuse.

### Stage 3: API and Worker Runtimes

**10. API Composition Root** - Build the FastAPI application: wire the adapters, mount the empty `/api/v1` router, configure CORS and request IDs, and install the global error-envelope handlers.

**11. Health Endpoint** - Implement `GET /health`, which reports database, migration, blob-store, git SHA and active-worker status with the 200/503 semantics in spec §5.

**12. Worker Runtime** - Implement the worker composition root, the job loop with its handler registry, the lease-renewal and expired-lease sweep cadence, the heartbeat thread, graceful signal-driven shutdown, and the built-in `noop` handler.

**13. Admin CLI** - Implement the `chatledger-admin` command with `enqueue-noop` and `job-status`, registered as a console script in the worker package.

### Stage 4: Containers, Web Shell and CI

**14. Dockerfiles and Compose Stack** - Write the API, worker and web images, including the git-SHA build stage. Write the compose file with the database, API (migrations before serving), two worker replicas and web, plus the named volumes, healthchecks and startup ordering.

**15. Design Tokens and UI Primitives** - Define the evidence-ledger design tokens and fonts. Build the token-styled Dialog, Tooltip and Toast wrappers and the shared EmptyState, Skeleton and ErrorBanner components.

**16. App Shell and Routes** - Build the root layout with side navigation, header slot and query provider. Add the root redirect, the Matters empty state with its "New matter" button, and the Reason Codes placeholder.

**17. Typed API Client and Status Banner** - Generate TypeScript types from the API's OpenAPI schema. Implement the typed client with error-envelope parsing, and the API status banner that polls the health endpoint and clears itself on recovery.

**18. CI Workflow** - Create the GitHub Actions workflow for push and pull requests, with a Python job (PostgreSQL 16 service) and a web job that both invoke the Makefile targets.

**19. README and ADRs** - Write the README with the three-command quick start, architecture diagram, benchmark table with pending rows, make-target reference and ADR index. Write the seven ADRs listed in the spec.

**20. Smoke Script** - Add the smoke script that boots the stack from a clean state, waits for health, checks the web shell and runs a `noop` job to completion.
