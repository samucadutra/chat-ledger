# ADR 0006 — Clean-architecture layering

## Status

Accepted (F01, 2026-10-01)

## Context

Parsing, modelling and gate logic must be testable without a database and
reviewable as pure code. The API and the worker share that logic, and later
features are built in parallel by different contributors.

## Decision

Python code lives in `packages/core/chatledger_core` with three layers:

- `domain` — entities, value objects, ports and errors. It imports nothing from
  the outer layers.
- `usecase` — orchestration. It imports only `domain`.
- `infra` — adapters for PostgreSQL, the filesystem and logging. It implements
  the domain ports.

`chatledger_api/main.py` and `chatledger_worker/main.py` are the composition
roots. They are the only places that instantiate adapters and read settings
(`chatledger_core/config.py` is the only module that reads the environment).
The rules are `import-linter` contracts run by `make lint`.

## Consequences

- Layer violations fail CI instead of code review.
- More files and indirection than a flat FastAPI layout.
- Domain and use-case tests run in milliseconds without PostgreSQL.
