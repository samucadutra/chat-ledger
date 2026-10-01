# ADR 0004 — Streaming JSON parsing

## Status

Accepted (F01, 2026-10-01)

## Context

Slack exports contain one JSON array per channel per day, and enterprise
exports can reach millions of messages. Loading whole files (or whole
exports) into memory makes worker memory proportional to input size and
crashes on the largest collections.

## Decision

Exports are read entry-by-entry from the archive and parsed with an
incremental (streaming) JSON parser. Parsed messages are written in batches
(PostgreSQL `COPY`) by work units sized to bound memory, and each work unit is a
queue job so parsing parallelises across workers.

## Consequences

- Worker memory is bounded by batch size, not input size.
- Malformed files fail only their work unit, with a precise reason code.
- Streaming parsers are slower per byte than `json.load`; parallel work units
  compensate.
- The `parsing` package is coverage-gated at 80% (see the Makefile `test` target).
