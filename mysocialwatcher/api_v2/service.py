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

    actions = writer.write(request.token, request.collection, normalized)
    results = [
        RowResult(
            source_index=row.source_index,
            status=200 if row.source_index in actions else 409,
            action=actions.get(row.source_index, "unchanged"),
            message={
                "inserted": "OK: row inserted.",
                "promoted": "OK: existing row promoted with refined estimates.",
                "unchanged": "Conflict: existing row retained.",
            }[actions.get(row.source_index, "unchanged")],
        )
        for row in normalized
    ]
    inserted = sum(action == "inserted" for action in actions.values())
    promoted = sum(action == "promoted" for action in actions.values())
    duplicates = len(normalized) - inserted - promoted
    return BatchWriteResponse(
        status=200,
        received=len(request.rows),
        accepted=len(normalized),
        rejected=len(errors),
        inserted=inserted,
        promoted=promoted,
        duplicates=duplicates,
        results=results,
        errors=errors,
    )
