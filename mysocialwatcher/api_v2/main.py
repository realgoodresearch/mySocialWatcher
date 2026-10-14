from fastapi import FastAPI, status

from mysocialwatcher.api_v2.schemas import HealthResponse


app = FastAPI(
    title="Social Watcher API",
    version="2.0.0-dev",
    docs_url="/socialwatcher/v2/docs",
    openapi_url="/socialwatcher/v2/openapi.json",
)


@app.get(
    "/socialwatcher/v2/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health() -> HealthResponse:
    """Report process health without accessing the database."""
    return HealthResponse()

