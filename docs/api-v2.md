# Social Watcher API v2 development guide

API v2 is an independent FastAPI batch-ingestion service. It does not replace Flask v1. The development container binds only to `127.0.0.1:8001`, and its disposable PostgreSQL instance binds to `127.0.0.1:55432`.

## Contract

`GET /socialwatcher/v2/health` checks process health without opening a database connection.

`POST /socialwatcher/v2/write-batch` accepts an envelope containing one token, one collection name, and 1–1,000 normalized rows. Invalid rows are returned in `errors` by `source_index`; valid rows remain eligible for the same transaction. Authentication failures return 401, and database failures roll back the batch and return 503.

The response reports aggregate `inserted`, `duplicates`, and `rejected` counts. It also returns one row-level result for every valid row: newly inserted rows receive status 200 and existing rows receive status 409. Validation failures remain status 400 in `errors`. Messages are concise and do not expose PostgreSQL error details. The crawler writes these statuses into its normal completion log, so a completed historical file can show whether it added data or consisted only of duplicates.

## Isolated development

Start the disposable API and database:

```bash
docker compose -p socialwatcher_v2_test \
  -f docker/api_v2/docker-compose.test.yml up -d --build --wait
```

The Compose project has its own network and volume. It does not join the production network or use production credentials.

Remove all test resources afterward:

```bash
docker compose -p socialwatcher_v2_test \
  -f docker/api_v2/docker-compose.test.yml down --volumes --remove-orphans
```

## Standalone file client

Parse a source file without sending or writing anything:

```bash
python3 utils/v2_batch_file.py SOURCE.csv.gz --collection COLLECTION
```

Sending requires `API_TOKEN`, `--send`, and a new explicit output path. It never writes into `data/crawler` automatically:

```bash
API_TOKEN=... python3 utils/v2_batch_file.py SOURCE.csv.gz \
  --collection COLLECTION \
  --url http://127.0.0.1:8001/socialwatcher/v2/write-batch \
  --output /tmp/v2-test-log.csv.gz --send
```

## Crawler selection

The existing crawler remains on v1 when `API_MODE` is absent:

```text
API_MODE=v1
```

V2 requires all three explicit settings:

```text
API_MODE=v2
API_URL=http://HOST:8001/socialwatcher/v2/write-batch
API_BATCH_SIZE=500
```

The crawler image supports both API versions; switching versions only requires changing these environment settings and recreating the crawler containers.

## Benchmark results

The isolated test ran 10,000 synthetic rows with batches of 500:

| Workload | Throughput |
|---|---:|
| One client, new rows | 4,899 rows/s |
| Four clients, new rows | 5,550 rows/s |
| Four clients, all duplicates | 5,662 rows/s |

An idle post-benchmark snapshot showed approximately 102 MiB for the API container and 87 MiB for PostgreSQL. These measurements use the minimal test schema on this server and are capacity indicators, not production guarantees.

A recent 3,822-row source file completed end to end with 3,822 accepted rows in the disposable database. A separate 399-row file with an existing all-200 v1 log parsed into 399 v2 rows without client errors.

The complete crawler lifecycle was also exercised against copied data. A restart skipped an existing completion log, and deleting only the copied log replayed the source without increasing database counts. In a synchronized test, four crawler containers each atomically claimed a different 3,822-row file; all four logs were complete and no temporary or error markers remained. Two other files produced the same 6 and 10 missing-audience 400s recorded by their existing v1 logs.

## Future deployment and rollback

Deployment requires a new v2 container on port 8001 and an explicit database URL. It does not require a database migration. Reverse-proxy routing and live crawler settings are separate production changes and are intentionally absent from this branch's development workflow.

The v2 service is part of the existing datahub Compose stack. Build and start that service explicitly so Compose does not recreate the running v1 services:

```bash
docker compose -f docker/datahub/docker-compose.yml up -d --build --wait --no-deps datahub_api_v2
curl --fail http://127.0.0.1:8001/socialwatcher/v2/health
```

It reads the existing database environment, shares the datahub network, and binds port 8001 only on localhost. Nginx routes `/socialwatcher/v2/` to this service.

Rollback is to set crawlers back to `API_MODE=v1` with the v1 URL, then stop the v2 container. V1 data and completion logs remain compatible because v2 writes to the existing tables and emits the same three crawler log columns.

Before any crawler has been switched, rollback consists only of removing v2:

```bash
docker compose -f docker/datahub/docker-compose.yml stop datahub_api_v2
docker compose -f docker/datahub/docker-compose.yml rm -f datahub_api_v2
```

## File registry database foundation (issue #5)

The datahub schema is now maintained in `docker/datahub/migrations/*.sql`.
`0001_initial.sql` preserves the existing tables, indexes, grants, seed records,
and country partitions. `0002_crawler_file_registry.sql` adds the registry and
transactional claim/completion functions. The API's SQLAlchemy table declarations
are query mappings, not an alternative schema creation mechanism.

On an empty PostgreSQL data directory, `initdb.sh` creates the writer/reader roles
and invokes `/schema/migrate.sh`. The datahub Compose definition mounts the schema
directory read-only. No migrations run automatically when the API starts or when
an existing PostgreSQL data directory is reused.

The migration runner requires explicit `POSTGRES_USER` and `POSTGRES_DB` settings;
standard libpq settings such as `PGHOST` and `PGPORT` select the server. Run it as
the schema owner. It uses a transaction and advisory lock, records SHA-256 checksums
in `schema_migrations`, skips applied versions, and rejects changed applied files.
Add new numbered SQL files instead of editing applied migrations. A failed run
rolls back its entire set of pending changes. The runner requires Bash, psql, and
sha256sum and can run without Python or the API dependencies.

Existing pre-migration installations require a one-time explicit adoption:
`bash docker/datahub/migrate.sh --baseline-legacy`. This checks that all nine legacy
tables exist, records migration 0001 without recreating tables or seed data, and
applies subsequent migrations in the same transaction. Before adopting a database,
compare its schema with 0001: the table-presence guard does not certify custom or
partially modified schemas. Subsequent upgrades use `bash docker/datahub/migrate.sh`.
Neither command has been run against production as part of this work.

`crawler_files` identifies decompressed CSV bytes by lowercase SHA-256 and retains
first-seen path and uncompressed byte size. `crawler_file_attempts` holds paths,
optional archive hash/size, collection, crawler, API and policy versions, retry
relationships, leases, outcomes, counts, and a bounded error summary. Paths must
be relative POSIX paths under `data/`, without traversal components. A caller must
also enforce containment when resolving paths on disk. Hashing, HTTP authentication,
API endpoints, lease renewal, and crawler dual-recording are subsequent rollout
work; this migration does not change crawler behavior or CSV logging.

The `crawler_claim(hash, path, uncompressed_size, collection, crawler_instance,
lease_seconds)` SQL function returns a decision, attempt ID, and secret claim token.
It serializes claims on the logical file and returns `process`, `retry`,
`in_progress`, or `already_completed`. An expired claim becomes an `abandoned`
attempt when reclaimed. Leases default to 900 seconds and must be 1–86400 seconds.
The future authenticated API should retain the token for completion and never log it.

`crawler_finish(id, token, outcome, total_rows, rows_200, rows_409, rows_400,
rows_401, rows_5xx, rows_other, corrupt_rows, error_summary)` accepts only a live
claim and returns false for stale, wrong, or previously finished claims. Counts
represent final per-source-row outcomes, not HTTP retry request counts. Successful
completion requires a known row total equal to terminal results. Policy `v1`
accepts only 200/409; no 400 categories have yet been approved. A future migration
and matching API policy must explicitly introduce accepted rejection categories.
Failures may have an unknown total and remain retryable. The functions use caller
privileges and are intended for the trusted API writer role; they are not an
HTTP authorization boundary. Writer has table access for recording optional attempt
metadata, and must use these functions for lease-sensitive state transitions.

Run the full isolated rebuild test with:

```bash
RUN_REGISTRY_REBUILD_TEST=1 python3 -m unittest utils.tests.test_registry_rebuild -v
```

It requires Docker and the `postgres:18` image. It creates a unique disposable
container with no network, host ports, or persistent data volume, mounts only the
schema files, and removes its own container afterward. It verifies clean init,
legacy upgrade equivalence, columns/constraints/indexes/partitions, migration
reruns and checksums, transaction rollback, concurrent migration runners, four
concurrent claimers, lease expiry, retry history, and terminal outcome enforcement.
The existing smaller API v2 test fixture remains available for ingestion tests.

Run the isolated API/crawler integration test with:

```bash
RUN_REGISTRY_E2E_TEST=1 python3 -m unittest utils.tests.test_registry_rebuild.RegistryEndToEndTests -v
```

It starts a fresh PostgreSQL database on tmpfs, the API v2 container, and a
crawler container on a unique internal-only Docker network. It verifies that
observation mode calls the real API routes, records the decompressed content
identity and terminal row counts, and still writes the existing CSV diagnostic
log. It publishes no ports and removes all disposable resources after the test.

### Observation-mode registry workflow

Migration `0003_crawler_registry_observation_api.sql` adds authenticated API v2
routes for `files/observe`, `files/claim`, lease renewal, and attempt completion.
Only observation mode is enabled in the crawler at this stage. Set
`API_MODE=v2`, `REGISTRY_MODE=observe`, `REGISTRY_URL` to the API v2 base URL,
and a stable `CRAWLER_INSTANCE` to opt in. `REGISTRY_MODE=off` remains the
default. Observation failures warn and do not prevent ingestion, CSV logging, or
the existing CSV-log skip rule. The crawler streams a SHA-256 over decompressed
CSV bytes, retains a separate archive hash, and sends only aggregate final HTTP
status counts to the registry.

`REGISTRY_MODE=enforce` is intentionally rejected until issue #6 establishes
order-independent better-estimate preference. Observed successful 409 outcomes
are diagnostic data, not permission to skip a file. No registry migration or
crawler configuration has been applied to production by this change.

## Registry next-step design (pending implementation)

This section records preparation for issue #5 while the daily crawl and issue #4 /
PR #4 review are pending. It does not describe currently available endpoints.
Implementation resumes after that review and merge, followed by rebasing
`feat/5-crawler-file-registry` onto `main`.

### Agreed compatibility and rollout

Keep one crawler codebase with independent ingestion API and registry settings.
Registry mode defaults to `off`. Both `observe` and `enforce` require API v2
ingestion; reject an incompatible configuration at startup before crawling.
All new API features belong under `/socialwatcher/v2/`; API v1 stays unchanged.

| Mode | File selection and processing | Registry behavior |
| --- | --- | --- |
| `off` | Existing behavior, including CSV-log-based skips | No registry requests or extra hashing |
| `observe` | Existing behavior, including CSV-log-based skips | Record identity and attempts without taking exclusive claims; registry failures do not gate ingestion |
| `enforce` | Registry claims and authoritative completion govern processing and skipping | Acquire and renew leases; record final outcomes |

Continue existing CSV diagnostics in all modes. Observations must be explicitly
marked and cannot automatically become authoritative completion. Any promotion of
observations or historical imports requires separate validation. Initial rollout
is opt-in observation; deployment alone must not enable registry behavior.

### Foundation review and required next migration

Migration 0002 predates the observation/enforcement agreement. Its current active
claim index applies to every `claimed` attempt, every attempt requires a lease,
and `crawler_claim` treats any completed attempt as authoritative. Calling these
functions unchanged from observation mode would violate the agreed behavior.

Add migration 0003 rather than editing checksummed migration 0002. It should:

- Distinguish observed attempts from enforced attempts. Existing 0002 attempts
  represent enforced claims; preserve that interpretation during upgrade.
- Allow observations to start and finish without an exclusive processing lease.
  Keep multiple observations of identical content possible.
- Restrict exclusive-claim indexes, expiry handling, and authoritative completion
  checks to enforced attempts. An observed success must not cause
  `already_completed`; an active observation must not cause `in_progress`.
- Separate observation completion from enforced completion and reject attempts to
  use one mode's operation on the other mode's attempt.
- Record the authenticated contributor that owns an attempt. Resolve ownership
  from the API write token, not a caller-supplied contributor ID or instance name.
- Add lease renewal using the same file lock order as claim and completion. Renew
  only an unexpired active claim, never revive an expired or superseded attempt.

### Proposed API contract

The following route names and HTTP behavior are implementation proposals; the
mode boundaries above are agreed requirements. Match the existing API v2 write
credential convention and redact credentials from errors and logs. Authenticate
before revealing registry state. Require attempt ownership and a secret attempt
token for mutations; a crawler instance name is diagnostic metadata, not identity.

All paths below are relative to `/socialwatcher/v2/`:

| Proposed POST route | Input and result |
| --- | --- |
| `files/observe` | Content hash, relative path, uncompressed size, collection, crawler instance, optional archive hash/size, and client request ID; returns an observation attempt handle, never a process/skip decision |
| `files/claim` | Same identity/context fields plus requested lease duration; returns `process`, `retry`, `in_progress`, or `already_completed`; only successful claims receive an attempt secret and lease expiry |
| `file-attempts/{id}/renew` | Attempt secret and requested lease duration; returns the new expiry for a live enforced claim |
| `file-attempts/{id}/finish` | Attempt secret, known or unknown total rows, final status counts, requested outcome, and bounded redacted error summary; validates according to the stored attempt mode and server-selected policy |

Keep HTTP status separate from per-row ingestion counts. Proposed responses are
200 for successful operations and claim decisions, 401 for invalid write
credentials, 404 for an inaccessible attempt, 409 for stale claims or conflicting
replays, 422 for malformed payloads, and 503 for database unavailability. Do not
return another crawler's attempt secret with `in_progress` or `already_completed`.

Use a client-generated request ID scoped to the authenticated owner for start
operations. Retrying an identical request after a lost response should recover
the same attempt; reusing an ID with different inputs should conflict. An exact
finish replay should acknowledge the stored result without another mutation;
a changed payload or superseded claim should conflict. Migration 0002 does not
yet provide these replay guarantees.

The server chooses completion policy `v1`, which accepts only 200/409. Final counts
represent source rows, not HTTP request attempts. Missing results, 400, 401, 5xx,
unknown statuses, and corrupt rows must prevent authoritative completion. Total
rows can be unknown for failure reporting; successful completion requires a known
and fully accounted total. Neither policy choice nor an accepted-400 count should
be an unrestricted caller-controlled way to declare success.

### Hashing and failure cases

Stream decompressed CSV bytes through SHA-256 with bounded memory. Do not
normalize CSV text or materialize the full file just to hash it. Renames and gzip
recompression preserve logical identity; byte changes do not. Hash the compressed
archive separately when requested. Validate relative paths and resolved containment
under `data/`, including symlink escapes, before reading.

Ensure ingestion uses the same bytes that were fingerprinted: a file modified
between hashing and ingestion must not be marked complete under the earlier hash.
A decompression failure has no trustworthy decompressed content hash. Never create
a logical file using a partial digest. Before implementation, choose how to retain
such pre-identity failures in the registry (for example a separate discovery-error
record with path and optional archive hash). Preserve existing CSV/error diagnostics
and retryability regardless of that choice.

Lease loss cannot cancel a batch already in flight. The enforced crawler should
stop scheduling further batches when it cannot establish that its lease remains
valid; stale claims cannot finalize completion. Existing ingestion deduplication
handles replayed rows. The registry guarantees exclusive valid claims, not that an
expired process can never finish an already-submitted HTTP request.

### Test plan before enabling observation

- Rebuild an empty database and upgrade a database at migration 0002 to identical
  schemas, retaining enforced attempts and prior migration checksums.
- Run concurrent observations and an enforced claim for the same content; verify
  observations neither block the claim nor affect its skip decision after finishing.
- Authenticate every registry route; reject read-only/invalid credentials and
  cross-owner attempt mutations without exposing secrets or request values.
- Race four claims, renewal against expiry/reclaim, and finish against reclaim;
  allow only one valid enforced claim and reject stale mutations.
- Simulate lost start/finish responses and conflicting request-ID replays; verify
  stable attempt history and immutable recorded completion.
- Exercise 200/409 completion, empty files, accepted totals, missing results,
  negative/overflowing counts, unknown totals, and every retryable error category.
- Hash identical CSV content across paths and gzip headers; test changed content,
  truncated gzip, bounded-memory streaming, path escapes, and source mutation.
- Verify registry `off` preserves current v1/v2 behavior; `observe` preserves CSV
  skips and processing during registry outages, with bounded request timeouts and
  diagnostics; v1 plus an enabled registry fails configuration validation.
- Verify `enforce` obeys claim decisions, renews long-running claims, stops new
  submissions on lease loss, and continues writing compatible CSV diagnostics.

Only disposable databases and test containers are needed for these checks.
Production migration, observation enablement, comparison over normal crawl cycles,
and later enforcement remain separate rollout steps.
