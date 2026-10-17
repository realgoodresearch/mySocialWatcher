from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

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


class RegistryStartRequest(BaseModel):
    token: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=4096)
    uncompressed_size: int = Field(ge=0)
    collection: str = Field(min_length=1, max_length=255)
    crawler_instance: str = Field(min_length=1, max_length=255)
    request_id: UUID
    archive_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    archive_size: int | None = Field(default=None, ge=0)
    lease_seconds: int = Field(default=900, ge=1, le=86400)


class RegistryStartResponse(BaseModel):
    decision: Literal["observe", "process", "retry", "in_progress", "already_completed"]
    attempt_id: int | None
    attempt_token: UUID | None
    lease_expires_at: str | None


class LeaseRenewRequest(BaseModel):
    token: str = Field(min_length=1)
    attempt_token: UUID
    lease_seconds: int = Field(default=900, ge=1, le=86400)


class LeaseRenewResponse(BaseModel):
    lease_expires_at: str


class AttemptFinishRequest(BaseModel):
    token: str = Field(min_length=1)
    attempt_token: UUID
    outcome: Literal["completed", "failed", "corrupt", "abandoned"]
    total_rows: int | None = Field(default=None, ge=0)
    rows_200: int = Field(default=0, ge=0)
    rows_409: int = Field(default=0, ge=0)
    rows_400: int = Field(default=0, ge=0)
    rows_401: int = Field(default=0, ge=0)
    rows_5xx: int = Field(default=0, ge=0)
    rows_other: int = Field(default=0, ge=0)
    corrupt_rows: int = Field(default=0, ge=0)
    error_summary: str | None = Field(default=None, max_length=1000)
