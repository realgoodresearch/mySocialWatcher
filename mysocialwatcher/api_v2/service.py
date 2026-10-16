from __future__ import annotations

from pydantic import ValidationError

from mysocialwatcher.api_v2.database import BatchWriter
from mysocialwatcher.api_v2.schemas import BatchWriteRequest, BatchWriteResponse, RowError, RowResult
from mysocialwatcher.api_v2.validation import normalize_row, validation_message


def process_batch(request: BatchWriteRequest, writer: BatchWriter) -> BatchWriteResponse:
    normalized = []
    errors = []
    seen_indices: set[int] = set()
    for position, raw in enumerate(request.rows):
        source_index = raw.get("source_index", position)
        try:
            row = normalize_row(raw)
            if row.source_index in seen_indices:
                raise ValueError("source_index must be unique within a batch")
            seen_indices.add(row.source_index)
            normalized.append(row)
        except (ValidationError, ValueError) as exc:
            errors.append(RowError(source_index=source_index if isinstance(source_index, int) else position,
                                   status=400, message=validation_message(exc)))

    inserted_indices = writer.write(request.token, request.collection, normalized)
    results = [
        RowResult(
            source_index=row.source_index,
            status=200 if row.source_index in inserted_indices else 409,
            message=("OK: row inserted." if row.source_index in inserted_indices
                     else "Conflict: row already exists."),
        )
        for row in normalized
    ]
    inserted = len(inserted_indices)
    duplicates = len(normalized) - inserted
    return BatchWriteResponse(
        status=200,
        received=len(request.rows),
        accepted=len(normalized),
        rejected=len(errors),
        inserted=inserted,
        duplicates=duplicates,
        results=results,
        errors=errors,
    )
