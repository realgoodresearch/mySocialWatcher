from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mysocialwatcher.api_v2.database import (
    AuthenticationError,
    BatchWriter,
    DatabaseWriteError,
    AttemptConflictError,
    RegistryWriter,
    engine_from_environment,
)
from mysocialwatcher.api_v2.schemas import (AttemptFinishRequest, BatchWriteRequest, BatchWriteResponse,
                                             HealthResponse, LeaseRenewRequest, LeaseRenewResponse,
                                             RegistryStartRequest, RegistryStartResponse)
from mysocialwatcher.api_v2.service import process_batch


app = FastAPI(
    title="Social Watcher API",
    version="2.0.0-dev",
    docs_url="/socialwatcher/v2/docs",
    openapi_url="/socialwatcher/v2/openapi.json",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return useful validation errors without echoing request values or tokens."""
    del request
    detail = [
        {
            "type": error["type"],
            "loc": error["loc"],
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={"detail": detail})


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


@lru_cache
def get_registry_writer() -> RegistryWriter:
    return RegistryWriter(engine_from_environment())


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


@app.post("/socialwatcher/v2/files/observe", response_model=RegistryStartResponse)
def observe_file(request: RegistryStartRequest, writer: RegistryWriter = Depends(get_registry_writer)):
    try:
        return writer.start("observe", request)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except DatabaseWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/socialwatcher/v2/files/claim", response_model=RegistryStartResponse)
def claim_file(request: RegistryStartRequest, writer: RegistryWriter = Depends(get_registry_writer)):
    try:
        return writer.start("enforce", request)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except DatabaseWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/socialwatcher/v2/file-attempts/{attempt_id}/renew", response_model=LeaseRenewResponse)
def renew_attempt(attempt_id: int, request: LeaseRenewRequest,
                  writer: RegistryWriter = Depends(get_registry_writer)):
    try:
        return {"lease_expires_at": writer.renew(attempt_id, request)}
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AttemptConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DatabaseWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/socialwatcher/v2/file-attempts/{attempt_id}/finish", status_code=status.HTTP_204_NO_CONTENT)
def finish_attempt(attempt_id: int, request: AttemptFinishRequest,
                   writer: RegistryWriter = Depends(get_registry_writer)):
    try:
        writer.finish(attempt_id, request)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AttemptConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DatabaseWriteError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
