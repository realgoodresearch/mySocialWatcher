# API v2 development status

Issue: https://github.com/realgoodresearch/mySocialWatcher/issues/3  
Branch: `feat/fastapi-v2-ingestion`

## Safety constraints

- Do not connect to or write to the production database.
- Do not restart, rebuild, reconfigure, or share resources with running containers.
- Development containers use a distinct Compose project, network, credentials, ports, and disposable volumes.
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
- [ ] Add standalone batch client and equivalence fixtures.
- [ ] Add opt-in crawler integration.
- [ ] Benchmark one and four isolated clients.
- [ ] Document future deployment and rollback without applying them.

## Validation record

- Built isolated image `mysocialwatcher-api-v2-dev:local` without changing running containers.
- `python -m unittest utils.tests.test_api_v2_validation`: 6 passed in the isolated image.
- Host Python has no Pydantic installation; v2 tests intentionally run in the isolated image.
- Unit and disposable PostgreSQL integration suite: 12 passed.
- HTTP smoke test on `127.0.0.1:8001`: health succeeded; a two-row batch inserted one row and returned one indexed 400; repeating it returned one duplicate.
- The `socialwatcher_v2_test` containers, network, and volume were removed after testing.
- Integration testing found that psycopg multi-row `rowcount` is `-1`; exact aggregate accounting now uses `INSERT ... ON CONFLICT DO NOTHING RETURNING 1`.

## Next action

Add the standalone CSV batch client and equivalence fixtures without writing live crawler logs.
