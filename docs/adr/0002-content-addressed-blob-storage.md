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
digest (`sha256/<first 2 hex>/<digest>.zip`). Database rows reference blobs by digest,
never by user-supplied file name. Blobs are written to a temporary file in the
same volume, hashed while streaming, then atomically renamed into place.

## Amendment (F02, 2026-10-02)

The final layout follows the PRD path and has a single fan-out level:

- **Path:** `{BLOB_ROOT}/sha256/{hex[0:2]}/{hex}.zip`. 256 directories are plenty
  for the expected number of collections.
- **Mode:** files are made read-only (`0444`) after the rename.
- **Staging:** uploads are written to `{BLOB_ROOT}/tmp/<uuid>.part` on the same
  volume while the SHA-256 is computed incrementally, so `os.replace` into the
  final path is atomic. Registration fsyncs the file and its directory.
- **Reuse:** if the digest already exists (another matter, or a blob left by a
  registration whose database transaction failed), the staged file is discarded
  and the stored one is reused after a size check. Orphaned blobs are harmless.
- **Janitor:** a thread in the API process deletes `tmp/*.part` files whose
  mtime is older than 10 minutes, every 60 seconds. Disconnects and errors
  delete the staged file immediately; the janitor covers API crashes.
- **Rejected uploads:** the staged file is deleted. Only the audit event
  (`collection.rejected`) records the SHA-256, size and reason.

## Consequences

- Deduplication across collections and re-deliveries is automatic.
- Integrity can be re-verified at any time by re-hashing.
- The digest doubles as an evidence fingerprint for manifests.
- Garbage collection needs reference counting (deferred until deletion exists).
- A local volume ties the PoC to one host; an S3-compatible adapter can
  implement the same port later.
