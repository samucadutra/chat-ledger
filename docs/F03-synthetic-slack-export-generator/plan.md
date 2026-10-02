# Implementation Plan: Synthetic Slack Export Generator

**Prerequisites:**
- F01 Project Foundation and F02 Matter and Collection Intake merged: job queue and worker runtime, `RegisterCollection`, blob store, migrations up to `0002_intake`, matters UI with the `actions` slot on the Collections tab
- uv, pnpm, Docker Compose, PostgreSQL 16 at `TEST_DATABASE_URL`, and `/usr/bin/time` available for the large-run check
- New settings from spec §4 added to `.env.example`, `.env.test` and the compose environment
- About 2 GB of free disk for the `large` acceptance run

### Stage 1: Deterministic Generator Core

**1. Generator Parameters and Presets** - Add the parameter model, preset tables and validation with the exact messages from spec assumptions A4-A6, as a pure domain module.

**2. Workspace Plan** - Build the seeded workspace plan: users, conversation type mix, Zipf volume allocation, day layout, sub-seeds and the fixed calendar, following decisions on determinism and day-file density.

**3. Conversation Renderer** - Render one conversation's day files with threads, mentions, links, reactions, file shares, bot messages and membership events, serialised as canonical JSON, per spec A8-A13.

**4. Anomaly Injection and Ground-Truth Model** - Implement the profile rate table, exact-count selection, the record mutations and the ground-truth record model with reason-code mapping and ordering, per spec A14-A16.

**5. Overlap Derivation** - Implement the re-delivery window, replay of base conversations for the window days and duplicate-source recording, per spec A17-A18.

### Stage 2: Output, Pipeline and CLI

**6. Deterministic ZIP and Ground-Truth Writers** - Implement the infra writers that emit sorted, fixed-metadata ZIP entries and the canonical streamed ground-truth JSON, both hashing their output while writing.

**7. Generation Pipeline Use Case** - Compose plan, rendering, anomaly collection and the writers into a streaming pipeline with disk-space pre-check, progress callback and cancellation check, honouring the memory and speed targets.

**8. Settings and Test Knobs** - Add the generator settings, including the inert test-only knobs, to configuration, environment examples and compose passthrough.

**9. Command-Line Tool** - Add the `chatledger-gen` console script with argument validation, progress lines on stderr, final path and SHA-256 report and the documented exit codes.

### Stage 3: Persistence and Worker Job

**10. Generation Migration and Repository** - Write migration `0003_generation` and the PostgreSQL repository, including the derived effective state that accounts for permanently failed jobs.

**11. Ground-Truth Storage Helpers** - Extend the blob store with the beside-the-blob ground-truth path, idempotent read-only write and conditional removal.

**12. Request, List, Get and Retry Use Cases** - Implement request validation with overlap-base resolution and parameter inheritance, enqueueing of the `generate` job, listing, reading and retry rules.

**13. Run-Generation Use Case and Worker Handler** - Implement the job body: running state, pipeline into staging, ground-truth storage, registration through the F02 entry point, outcome classification, orphan-registration adoption and cleanup, then register the `generate` kind in the worker.

### Stage 4: API

**14. Generation Routes** - Add create, list, get and retry endpoints under the matter, with the error codes in spec §5, and wire the use cases in the API composition root.

**15. Ground-Truth Download and Collection Payload** - Add the per-collection ground-truth download route and extend the F02 collection payload with the `generation` object; regenerate the OpenAPI client types.

### Stage 5: Web and Verification Tooling

**16. Generate Dialog** - Build the modal with seed, preset, custom fields, profile descriptions and re-delivery dropdown, sharing validation rules and messages with the API.

**17. Generation Cards and Polling** - Show pending, failed and duplicate cards with progress, polling every 2 seconds, and the Retry rules; convert finished generations into normal collection cards.

**18. Synthetic Badge and Ground-Truth Link** - Extend the collection card and the Collections tab header with the button, the "Synthetic" badge and the download link.

**19. Fixtures and Perf Script** - Add the ground-truth JSON Schema fixture and the large-run performance script that checks time, peak memory and record counts.

**20. Documentation and Gates** - Update README usage notes for the CLI and the UI flow, add the import-linter entries for the new package, and make sure `make check` passes.
