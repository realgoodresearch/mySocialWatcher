from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, status

from mysocialwatcher.api_v2.database import (
    AuthenticationError,
    BatchWriter,
    DatabaseWriteError,
    engine_from_environment,
)
from mysocialwatcher.api_v2.schemas import BatchWriteRequest, BatchWriteResponse, HealthResponse
from mysocialwatcher.api_v2.service import process_batch


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


@lru_cache
def get_writer() -> BatchWriter:
    return BatchWriter(engine_from_environment())


@app.post("/socialwatcher/v2/write-batch", response_model=BatchWriteResponse)
def write_batch(
    request: BatchWriteRequest,
    writer: BatchWriter = Depends(get_writer),
) -> BatchWriteResponse:
    try:
        return process_batch(request, writer)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except DatabaseWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
