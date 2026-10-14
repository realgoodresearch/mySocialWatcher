from __future__ import annotations

import datetime
import json
from ast import literal_eval
from collections.abc import Iterator

import numpy
import pandas as pd
import requests


def parse_response(value):
    if not isinstance(value, str) or not value:
        raise ValueError("response must be a non-empty string")
    if value.startswith("b'") or value.startswith('b"'):
        return json.loads(literal_eval(value).decode("utf-8"))
    if value.startswith("{"):
        return json.loads(value)
    if value.startswith("["):
        return literal_eval(value)
    raise ValueError("unrecognized response representation")


def dataframe_to_v2_rows(dataframe: pd.DataFrame) -> tuple[list[dict], dict[int, str]]:
    rows: list[dict] = []
    errors: dict[int, str] = {}
    for position, row in enumerate(dataframe.itertuples(index=False)):
        try:
            platforms = literal_eval(row.publisher_platforms)
            if len(platforms) != 1:
                raise ValueError("exactly one publisher platform is required")
            ages = literal_eval(row.ages_ranges)
            age_min, age_max = ((ages.get("min"), ages.get("max"))
                                if isinstance(ages, dict) else (ages[0], ages[1]))
            all_fields = dict(literal_eval(row.all_fields))
            payload = {
                "source_index": position,
                "platform": platforms[0],
                "timestamp": row.timestamp,
                "gender": row.genders,
                "age_min": age_min,
                "age_max": age_max,
                "dau": row.dau_audience,
                "mau": row.mau_audience,
                "mau_upper": getattr(row, "mau_audience_upper_bound", None),
                "mau_lower": getattr(row, "mau_audience_lower_bound", None),
                "valid": True,
                "geo_locations": all_fields["geo_locations"],
                "all_fields": all_fields,
                "targeting": literal_eval(row.targeting),
                "response": parse_response(row.response),
            }
            payload = {
                key: (int(value) if isinstance(value, numpy.integer) else value)
                for key, value in payload.items()
                if value is not None and not (isinstance(value, float) and pd.isna(value))
            }
            rows.append(payload)
        except Exception as exc:
            errors[position] = f"CLIENT VALIDATION: {exc}"
    return rows, errors


def chunks(values: list[dict], size: int) -> Iterator[list[dict]]:
    if size < 1 or size > 1000:
        raise ValueError("batch size must be between 1 and 1000")
    for start in range(0, len(values), size):
        yield values[start:start + size]


def submit_dataframe_v2(
    dataframe: pd.DataFrame,
    collection: str,
    token: str,
    url: str,
    batch_size: int = 500,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    rows, errors = dataframe_to_v2_rows(dataframe)
    results: dict[int, tuple[int, str]] = {
        index: (400, message) for index, message in errors.items()
    }
    client = session or requests.Session()
    for batch in chunks(rows, batch_size):
        response = client.post(
            url,
            json={"token": token, "collection": collection, "rows": batch},
            timeout=(10, 300),
        )
        response.raise_for_status()
        body = response.json()
        rejected = {item["source_index"]: item for item in body["errors"]}
        for row in batch:
            index = row["source_index"]
            if index in rejected:
                item = rejected[index]
                results[index] = (item["status"], item["message"])
            else:
                results[index] = (200, "OK: accepted (inserted or already present).")

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return pd.DataFrame({
        "timestamp_api": [now] * len(dataframe),
        "status_api": [results[index][0] for index in range(len(dataframe))],
        "message_api": [results[index][1] for index in range(len(dataframe))],
    })
