# API v2 development status

Issue: https://github.com/realgoodresearch/mySocialWatcher/issues/3  
Branch: `feat/fastapi-v2-ingestion`

## Deployment constraints

- Production tests use the dedicated test contributor and token.
- Do not restart or reconfigure API v1, nginx, the database, or production crawlers while validating v2.
- Crawler tests use copied files and disposable directories.
- API v2 listens on host port 8001.
- Flask API v1, nginx, and the production crawler configuration remain unchanged.
- Batch crawler behavior is opt-in; v1 remains the default.

## Decisions

- V2 is a separate FastAPI application, initially limited to health and batch ingestion.
- A request contains at most 1,000 normalized rows; the initial client default will be 500.
- Envelope errors use HTTP status codes. Individual bad rows are returned as indexed results and do not reject otherwise valid rows.
- Accepted rows and existing duplicates both count as accounted for. Unexpected database errors roll back the affected batch.
- The crawler continues to parse legacy CSV representations. The API receives JSON objects, not Python-literal strings.
- SQL is parameterized. V1's SQL-quoting transformations are not reused.

## Progress

- [x] Record safety constraints and initial contract decisions.
- [x] Scaffold FastAPI application and request/response schemas.
- [x] Implement pure row normalization and validation with regression tests.
- [x] Implement isolated authentication and bulk database layer.
- [x] Add disposable PostgreSQL integration environment and tests.
- [x] Add standalone batch client and equivalence fixtures.
- [x] Add opt-in crawler integration.
- [x] Benchmark one and four isolated clients.
- [x] Add v2 to the datahub Compose stack and deploy it alongside v1.
- [x] Validate a real insert, duplicate replay, and completion-log skip with an isolated crawler.

## Validation record

- Built isolated image `mysocialwatcher-api-v2-dev:local` without changing running containers.
- `python -m unittest utils.tests.test_api_v2_validation`: 6 passed in the isolated image.
- Host Python has no Pydantic installation; v2 tests intentionally run in the isolated image.
- Unit and disposable PostgreSQL integration suite: 12 passed.
- HTTP smoke test on `127.0.0.1:8001`: health succeeded; a two-row batch inserted one row and returned one indexed 400; repeating it returned one duplicate.
- The `socialwatcher_v2_test` containers, network, and volume were removed after testing.
- Integration testing found that psycopg multi-row `rowcount` is `-1`; exact aggregate accounting now uses `INSERT ... ON CONFLICT DO NOTHING RETURNING 1`.
- API/service/route unit suite: 13 passed; crawler batch/mode suite: 4 passed.
- Recent source parse: 3,822/3,822 rows; disposable end-to-end insert and test log: 3,822 status 200.
- A 399-row source with an existing all-200 v1 log parsed 399/399 for v2 with no client errors.
- Synthetic batches of 500: 4,899 rows/s (one client), 5,550 rows/s (four clients), and 5,662 rows/s (four-client duplicate replay).
- Post-benchmark idle memory snapshot: API 101.8 MiB; PostgreSQL 86.83 MiB.
- Full crawler lifecycle against copied data and the disposable database:
  - one 399-row file produced one complete log, no stale markers, 342 valid rows, and 57 intentionally invalid rows;
  - restarting skipped the completed file;
  - removing the copied log replayed safely without increasing database counts;
  - four synchronized replicas each claimed a different 3,822-row file and produced four complete logs with no stale markers;
  - 16 missing-audience 400s in two additional files matched their existing v1 logs exactly;
  - isolated API logs contained no server errors.
- All crawler test containers, copied files, networks, and disposable volumes were removed after verification.
- Production deployment validation:
  - `datahub_api_v2` remained healthy on `127.0.0.1:8001` alongside v1;
  - read-only database connectivity succeeded;
  - a known completed 399-row file returned 399 duplicates and zero inserts;
  - an uncrawled 105-row Aruba Instagram file created 105 rows under the dedicated test contributor and a 105-row all-200 completion log;
  - replay left the database count at 105, and restart with the completion log skipped the file;
  - the production crawler containers remained stopped throughout the live crawler test.

## Next action

Rotate the exposed test token, then run a small four-replica copied workload against v2 before changing the production crawler configuration.
