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
- [ ] Implement isolated authentication and bulk database layer.
- [ ] Add disposable PostgreSQL integration environment and tests.
- [ ] Add standalone batch client and equivalence fixtures.
- [ ] Add opt-in crawler integration.
- [ ] Benchmark one and four isolated clients.
- [ ] Document future deployment and rollback without applying them.

## Validation record

- Built isolated image `mysocialwatcher-api-v2-dev:local` without changing running containers.
- `python -m unittest utils.tests.test_api_v2_validation`: 6 passed in the isolated image.
- Host Python has no Pydantic installation; v2 tests intentionally run in the isolated image.

## Next action

Implement isolated authentication, collection registration, and bulk database transactions.
