# ADR 0005 — Reason-code accounting

## Status

Accepted (F01, 2026-10-01)

## Context

A defensible production must explain every message that was received but not
produced: duplicates, out-of-range dates, unparseable records, unsupported
subtypes. "We dropped some messages" is not an acceptable answer to opposing
counsel.

## Decision

Every input message ends a run in exactly one terminal bucket: exported, or
excluded with exactly one reason code from a fixed catalogue. Quality gates
verify the accounting equation `received = exported + Σ excluded(reason)` per
conversation and per run, and a run cannot be marked complete if it does not
balance.

## Consequences

- Completeness reports are exact and auditable.
- Every new exclusion path must register a reason code (enforced by tests in
  the `gates` package, coverage-gated at 80%).
- The catalogue is product surface: it is listed in the UI (Reason Codes) and in
  export manifests.
