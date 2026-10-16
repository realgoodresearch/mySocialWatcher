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
