# Implementation Plan: Matter and Collection Intake

**Prerequisites:**
- F01 Project Foundation merged: workspace, Makefile gates, migration `0001_foundation`, `AuditLog`, error envelope and web shell
- uv, pnpm, Docker Compose, and PostgreSQL 16 reachable at `TEST_DATABASE_URL`
- New settings from spec §4 added to `.env.example` and `.env.test`
- About 4 GB of free disk for the generated large fixtures

### Stage 1: Domain, Persistence and Blob Store

**1. Intake Domain Model** - Add the matter, collection and archive value objects, the typed intake errors and the intake ports to the core domain layer, as listed in spec §4.

**2. Archive Rules** - Implement the pure archive inspection function. It applies the ordered safety rules, detects the Slack export markers and root prefix, and derives entry count, conversation count and day-file date range, following the spec's assumptions A4–A7.

**3. Intake Migration** - Write migration `0002_intake`, which creates the matter, blob and collection tables with the indexes and constraints from spec §6.

**4. Repositories and Blob Store Adapters** - Implement the PostgreSQL matter and collection repositories, the filesystem blob store with the content-addressed layout and read-only files, the streaming staging writer with its stale-file sweep, and the ZIP central-directory inspector.

### Stage 2: Use Cases and API

**5. Matter Use Cases** - Implement create, list and get for matters, including name normalisation, case-insensitive uniqueness and the `matter.created` audit event.

**6. Collection Registration Use Case** - Implement the shared registration entry point. It hashes and inspects the staged file, then in one transaction locks the matter, enforces the duplicate and cap rules, stores or reuses the blob, inserts rows and audits. Rejections clean up the staged file and record `collection.rejected`.

**7. Settings and Composition Root** - Add the intake limits to settings and wire the new adapters and use cases into the API composition root. Start the stale-upload janitor in the API lifespan.

**8. Matter and Collection Routes** - Add the six `/api/v1/matters` endpoints, including the raw streaming upload with header validation, early size rejection, disconnect cleanup and the error codes listed in spec §5.

### Stage 3: Web Experience

**9. Typed Client and Intake API Module** - Regenerate the OpenAPI types. Add the intake API calls and the XHR-based upload client with progress, speed, abort and interrupted-upload handling.

**10. Matters Ledger and New Matter Dialog** - Replace the static matters page with the ledger table backed by the API, keeping the empty state for zero matters. Add the New matter dialog with inline validation and navigation to the new matter.

**11. Matter Layout and Tabs** - Add the matter route layout with page header, current-matter header context, the not-found state and the route-based tab bar with the four run-dependent tabs disabled.

**12. Collections Tab** - Build the drop zone with client-side checks, the upload row (uploading, verifying, error and interrupted states) and the collection cards with hash copy, counts and date range. Leave an actions slot for later features.

### Stage 4: Fixtures and Documentation

**13. Intake Fixtures** - Create the deterministic fixture generator. Commit the small valid and hostile ZIP fixtures, and add the `fixtures-intake` Makefile target that writes the large generated fixtures into the gitignored folder.

**14. Documentation Updates** - Amend ADR 0002 with the final blob layout, staging directory and janitor behaviour. Add an intake section to the README describing limits and validation rules.
