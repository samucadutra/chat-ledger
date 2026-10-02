# Implementation Plan: Inventory and Streaming Ingestion

**Prerequisites:**
- F01 Project Foundation and F02 Matter and Collection Intake merged: workspace, Makefile gates, migrations `0001_foundation` and `0002_intake`, `JobQueue`, `AuditLog`, worker loop, `RegisterCollection`, blob store
- uv, pnpm, Docker Compose, and PostgreSQL 16 reachable at `TEST_DATABASE_URL`
- `ijson` (with its C backend) added to the core package dependencies
- New settings from spec §4 added to `.env.example`, `.env.test` and the compose environment
- About 6 GB of free disk for the generated large fixtures, and a machine comparable to the PRD reference (8 cores, 16 GB) for the throughput and memory checks

### Stage 1: Domain, Parsing and Persistence

**1. Ingestion Domain Model** - Add the run aggregate with its state machine and settings hashing, the work unit, inventory, quarantine and parsed-record value objects, the typed errors and the ports, as listed in spec §4. Include the default gate thresholds recorded in the spec assumptions.

**2. Streaming Utilities and Error Offsets** - Build the counting reader, the batcher and the error offset locator in the parsing package, following spec assumption A9, so that malformed input yields exact byte offsets.

**3. Slack Parsing Rules** - Implement entry classification, folder-to-conversation resolution, workspace metadata parsing, record validation in the documented order, and referenced-user extraction. Compose them into the Slack `SourceParser` with `inventory()`, `units()` and `parse_unit()`.

**4. Ingestion Migration** - Write migration `0003_ingestion` with the tables, indexes, constraints and the append-only quarantine trigger from spec §6.

**5. Repositories, Staging Sink and ZIP Reader** - Implement the PostgreSQL adapters for runs, inventory, units and quarantine, the `COPY`-based staging sink, the provided read-model readers, and the ZIP entry reader that works from the central directory without extracting to disk.

**6. Queue Extension** - Add the bulk cancellation of queued jobs by group key to the queue port and its PostgreSQL adapter.

### Stage 2: Run Lifecycle Use Cases

**7. Settings and Start Run** - Add the ingestion settings and fault-injection knobs. Implement the start-run use case, which freezes the collections and settings, enforces the one-active-run rule under the matter lock, enqueues the inventory job and audits the start.

**8. Inventory Stage** - Implement the inventory use case. It re-verifies each blob, records every entry with its hash and kind, stores workspace metadata, computes the input inventory hash and team ID, creates one unit per conversation and enqueues the unit jobs. Integrity and read failures end the run as `failed` with the audit event.

**9. Unit Processing** - Implement the unit use case. One transaction per attempt streams the day files in order, validates and quarantines records, flushes batches, maintains counts and referenced users, reports live progress, honours cancellation and lease loss, and applies fault injection.

**10. Run Coordinator and Stage Hooks** - Implement the coordinator that syncs unit outcomes, advances stages through the stage handler registry with pass-through defaults, finalizes runs and writes the finish audit event. Add the database outage failure rule.

**11. Cancel and Read Use Cases** - Implement run cancellation with its state rules and the get, list, inventory and quarantine read use cases, including the derived progress figures.

### Stage 3: API and Worker Wiring

**12. Run Routes** - Add the six `/api/v1` endpoints with request and response models, query validation and the error codes from spec §5, and mount them in the versioned router.

**13. Worker Handlers** - Add the inventory and unit handlers, register them, give the loop a sweep callback that runs the coordinator, and add the outage tracker to the worker composition root.

**14. Composition Roots** - Wire the new adapters, use cases and stage registry into the API and worker entry points, and pass the new environment variables through the compose file.

**15. Structured Logging** - Emit the structured worker log lines (run ID, unit ID, stage, records, elapsed milliseconds) from the handlers and the coordinator.

### Stage 4: Fixtures and End-to-End Tooling

**16. Ingestion Fixtures** - Create the deterministic fixture generator and commit the small valid and defective ZIPs with the expected-counts file. Add the `fixtures-ingestion` Makefile target for the large generated inputs.

**17. End-to-End Scripts** - Write the throughput, memory, crash-recovery, cancel, integrity and hashing-speed scripts, plus the `e2e-ingest` Makefile target.

### Stage 5: Contracts, Types and Documentation

**18. Architecture Rules and Types** - Add the import-linter contract that keeps the parsing package dependent on the domain layer only, and regenerate the web API types from the OpenAPI schema.

**19. Documentation Updates** - Amend ADR 0004 with the staging design, batch size and offset behaviour, and add an ingestion section to the README covering run states, reason codes, limits and the fixture and E2E commands.
