# ADR 0002 — Content-addressed blob storage

## Status

Accepted (F01, 2026-10-01)

## Context

Collections are multi-gigabyte Slack exports, and runs produce derived files
(RSMF packages, manifests, reports). Evidence handling requires proving that
an input or output is byte-identical to what was received or delivered, and
re-deliveries frequently contain files already seen.

## Decision

Binary payloads are stored on a named Docker volume (`blobstore`, mounted at
`/data/blobs` in `api` and `worker`) under a path derived from their SHA-256
digest (`sha256/ab/cd/<digest>`). Database rows reference blobs by digest,
never by user-supplied file name. Blobs are written to a temporary file in the
same volume, hashed while streaming, then atomically renamed into place.

## Consequences

- Deduplication across collections and re-deliveries is automatic.
- Integrity can be re-verified at any time by re-hashing.
- The digest doubles as an evidence fingerprint for manifests.
- Garbage collection needs reference counting (deferred until deletion exists).
- A local volume ties the PoC to one host; an S3-compatible adapter can
  implement the same port later.
