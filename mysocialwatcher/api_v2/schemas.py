from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BatchWriteRequest(BaseModel):
    token: str = Field(min_length=1)
    collection: str = Field(min_length=1, max_length=50)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class RowError(BaseModel):
    source_index: int
    status: Literal[400]
    message: str


class RowResult(BaseModel):
    source_index: int
    status: Literal[200, 409]
    message: str


class BatchWriteResponse(BaseModel):
    status: Literal[200]
    received: int
    accepted: int
    rejected: int
    inserted: int
    duplicates: int
    results: list[RowResult]
    errors: list[RowError]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["socialwatcher-api-v2"] = "socialwatcher-api-v2"
