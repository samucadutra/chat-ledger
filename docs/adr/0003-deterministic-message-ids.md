# ADR 0003 — Deterministic message IDs

## Status

Accepted (F01, 2026-10-01)

## Context

The same Slack message can appear in several exports (overlapping date ranges,
re-deliveries, edits). Reviewers and the run-diff tool must be able to say
"this is the same message" across runs, and two runs over the same inputs must
produce identical outputs.

## Decision

A message's ID is a hash of its stable coordinates — workspace ID, conversation
ID and Slack `ts` — and never of its content, collection or run. IDs are
computed in `chatledger_core` so every component derives them identically.

## Consequences

- Edits and re-deliveries map onto the same message ID; content changes are
  tracked as versions, not new messages.
- Outputs are reproducible: identical inputs yield identical IDs and files.
- A Slack `ts` collision inside one conversation (not expected from Slack) would
  merge two messages; the parser reports it as a quality-gate finding.
