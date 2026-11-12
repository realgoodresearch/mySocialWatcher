# Social Watcher API v2

API v2 is the production FastAPI service for batch ingestion and crawler file-registry operations. Flask API v1 remains available for existing read clients.

Documentation is currently available through the internal datahub route:

- `http://serenity/socialwatcher/v2`
- `http://serenity/socialwatcher/v2/docs`
- OpenAPI schema: `http://serenity/socialwatcher/v2/openapi.json`

Public routing through `api.realgoodresearch.com` is deferred until issue #10
completes the remaining v2 API.

All paths below are relative to `/socialwatcher/v2`.

## Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Process health without a database query |
| `POST /write-batch` | Validate and write 1–1,000 normalized audience rows |
| `POST /files/observe` | Record a non-authoritative file observation |
| `POST /files/claim` | Claim logical file content for exclusive processing |
| `POST /file-attempts/{id}/renew` | Renew an active enforced claim |
| `POST /file-attempts/{id}/finish` | Record terminal file and row outcomes |

The authenticated endpoints currently accept a `token` field in their JSON request. The token must have `write=true`; invalid and read-only tokens receive HTTP 401. Never place production tokens in source files, logs, issue comments, or command history.

## Batch ingestion

`POST /write-batch` accepts an envelope containing a token, collection name, and 1–1,000 normalized rows:

```json
{
  "token": "...",
  "collection": "example_collection",
  "rows": [
    {
      "publisher_platforms": ["facebook"],
      "timestamp": 1793491200,
      "genders": 0,
      "ages_ranges": {"min": 18, "max": 65},
      "dau_audience": -1,
      "mau_audience": 1000,
      "all_fields": {
        "geo_locations": {"name": "countries", "values": ["GB"]}
      },
      "targeting": {},
      "response": {"data": [{"estimate_ready": true}]}
    }
  ]
}
```

The API returns one terminal action for every source row:

- `inserted`: a new database row was written;
- `promoted`: an existing original row was updated with refined estimates;
- `unchanged`: the preferred row was already present;
- `rejected`: the source row failed API validation.

Valid rows in a mixed batch remain eligible when other rows are rejected. Authentication failures return 401, request-schema failures return 422, and database failures roll back the batch and return 503.

Meta stopped returning DAU estimates on 2026-10-27. Omitted DAU is therefore normalized to the valid `-1` sentinel. The original Meta response JSON is preserved exactly. At least one MAU value or bound is still required. Rows explicitly marked `estimate_ready=false` are rejected; responses without that field remain subject to the other validity checks.

Refined rows are identified by the `better_estimates` marker stored in `all_fields`. When an original row already occupies the unique identity, API v2 promotes its MAU values and marker in place and sets `updated_on`. `contributed_on` continues to identify the original insertion time.

## File registry

The registry identifies logical source content using the SHA-256 digest and size of the decompressed CSV bytes. It also retains the compressed archive digest, archive size, relative path, collection, crawler identity, contributor, attempts, leases, outcomes, and row counts.

Identical decompressed content is authoritative even if its path or gzip representation changes. Relative paths must remain beneath `DATA_DIR` and may not contain traversal components.

### Claim lifecycle

`POST /files/claim` returns one of:

- `process`: new logical content was claimed;
- `retry`: a failed or expired attempt was reclaimed;
- `in_progress`: another crawler owns a live lease;
- `already_completed`: an enforced attempt already completed the content.

Only `process` and `retry` return an attempt ID, secret attempt token, and lease expiry. The crawler renews the lease between ingestion batches. Completion requires the authenticated owner, attempt secret, a terminal outcome, and row counts that reconcile to the source total.

Completed and completed-with-rejections attempts are authoritative. Failed, corrupt, abandoned, and expired work remains retryable. Registry observations are diagnostic and never block or satisfy an enforced claim.

### Registry database schema

`crawler_files` stores logical content identities. `crawler_file_attempts` stores each observation or enforced processing attempt. Database functions serialize claims, renew leases, validate ownership, and enforce terminal count invariants. Only the PostgreSQL writer role can mutate registry state.

## Production crawler workflow

The production crawler uses API v2 with registry enforcement. Its essential `.env` settings are:

```dotenv
DATA_DIR=data
CRAWLER_REPLICAS=4
API_URL=http://serenity/socialwatcher/v2/write-batch
API_BATCH_SIZE=500
REGISTRY_URL=http://serenity/socialwatcher/v2
REGISTRY_LEASE_SECONDS=900
CRAWLER_INSTANCE=daily-crawler
```

The crawler discovers eligible `finished/dataframe_collected_finished_*.csv.gz` files, sorts them by modification time newest first, and asks the registry whether each content identity requires processing. Existing legacy crawler logs do not prevent an enforced claim. New durable row reports are written beneath `data/crawler/registry/`; legacy logs remain unchanged.

Enforced claims coordinate replicas, so registry-based crawls do not use `temp.txt` claim markers. A restart safely skips completed content and retries interrupted work after its lease expires.

### Optional selection filters

Date bounds use the `YYYYMMDD` suffix in source filenames and are inclusive:

```dotenv
CRAWL_DATE_FROM=2026-10-01
CRAWL_DATE_TO=2026-10-31
# CRAWL_PATH_PREFIX=serenity/migration_asia_pacific/
```

Omit `CRAWL_DATE_TO` for an open upper bound. Do not assign it an empty value; an empty string is not a valid ISO date. Omit all filters to consider every eligible source file.

### Daily operation

From the repository root, synchronize source data and restart the standard replicas with:

```bash
./utils/daily_crawl.sh ./
```

When source data are already current, use:

```bash
./utils/daily_crawl_nosync.sh ./
```

The production cron job runs the synchronized workflow at midnight. It stops the standard crawler project, synchronizes incoming files, removes stale legacy markers, and restarts the replicas. Newly synchronized files are considered first; registry-completed content is skipped before the crawler continues through older files.

## Database migrations

Schema history lives in `docker/datahub/migrations/*.sql`. `initdb.sh` creates the reader and writer roles for a new database and invokes `docker/datahub/migrate.sh`. Existing PostgreSQL data directories do not run migrations automatically when an API container starts.

Run pending migrations explicitly as the schema owner:

```bash
bash docker/datahub/migrate.sh
```

An installation predating the migration ledger requires one explicit adoption:

```bash
bash docker/datahub/migrate.sh --baseline-legacy
```

The migration runner uses a transaction and advisory lock, records SHA-256 checksums, skips applied versions, and rejects edits to applied migrations. Add a new numbered migration instead of changing a migration already recorded in production.

## Deployment

API v2 is the `datahub_api_v2` service in the datahub Compose stack. It shares the datahub network, connects to the production database through the writer role, and binds port 8001 only on localhost. Nginx proxies `/socialwatcher/v2` to that service.

Build and recreate only API v2 so the production database and v1 services are not restarted:

```bash
docker compose -f docker/datahub/docker-compose.yml \
  up -d --build --no-deps datahub_api_v2
```

Verify the direct and proxied routes:

```bash
curl --fail http://127.0.0.1:8001/socialwatcher/v2/health
curl --fail http://serenity/socialwatcher/v2/health
curl --fail --location http://serenity/socialwatcher/v2
```

Recreating API v2 can change its container address. If nginx retains the old upstream address, validate and reload it:

```bash
docker exec datahub_web nginx -t
docker exec datahub_web nginx -s reload
```

Avoid recreating API v2 during an active crawl; a brief proxy failure creates retryable registry attempts and unnecessary ingestion delay.

## Isolated development and tests

Start the disposable API and PostgreSQL environment:

```bash
docker compose -p socialwatcher_v2_test \
  -f docker/api_v2/docker-compose.test.yml up -d --build --wait
```

Remove it afterward:

```bash
docker compose -p socialwatcher_v2_test \
  -f docker/api_v2/docker-compose.test.yml down --volumes --remove-orphans
```

The full registry schema rebuild test creates only a unique disposable PostgreSQL container:

```bash
RUN_REGISTRY_REBUILD_TEST=1 \
  python3 -m unittest utils.tests.test_registry_rebuild -v
```

The API/crawler end-to-end test uses an isolated Docker network, disposable PostgreSQL, and no production ports or credentials:

```bash
RUN_REGISTRY_E2E_TEST=1 \
  python3 -m unittest \
  utils.tests.test_registry_rebuild.RegistryEndToEndTests -v
```

## Recovery and legacy crawler

The registry is the production completion authority. Deleting a CSV report does not make completed content eligible again. Preserve registry records and diagnostic reports during routine cleanup.

The unchanged pre-registry crawler is archived in Git tag `legacy-crawler-pre-registry`. Use that tag only for deliberate legacy recovery work; production uses the registry-based crawler.

API v1 remains available for existing read clients. Removal or redirection of v1 is outside the registry rollout and requires a separate migration decision.
