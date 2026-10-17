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
