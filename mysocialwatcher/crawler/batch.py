from __future__ import annotations

import datetime
import json
from pathlib import Path
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


def mark_better_estimates(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with explicit provenance for legacy refinement files."""
    marked = dataframe.copy()

    def add_marker(value):
        parsed = literal_eval(value) if isinstance(value, str) else value
        fields = dict(parsed)
        fields["better_estimates"] = True
        return repr(tuple(fields.items()))

    marked["all_fields"] = marked["all_fields"].apply(add_marker)
    return marked


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
    checkpoint_path: Path | None = None,
) -> pd.DataFrame:
    rows, errors = dataframe_to_v2_rows(dataframe)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    results: dict[int, tuple[str, int, str, str]] = {
        index: (now, 400, "rejected", message) for index, message in errors.items()
    }
    if checkpoint_path is not None and checkpoint_path.exists():
        prior = pd.read_csv(checkpoint_path, index_col=0)
        for index, item in prior.iterrows():
            results[int(index)] = (
                str(item["timestamp_api"]), int(item["status_api"]),
                str(item["action_api"]), str(item["message_api"]),
            )

    def checkpoint() -> None:
        if checkpoint_path is None:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        partial = result_frame(results)
        temporary = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
        partial.to_csv(temporary, compression="gzip")
        temporary.replace(checkpoint_path)

    checkpoint()
    client = session or requests.Session()
    pending = [row for row in rows if row["source_index"] not in results]
    for batch in chunks(pending, batch_size):
        response = client.post(
            url,
            json={"token": token, "collection": collection, "rows": batch},
            timeout=(10, 300),
        )
        response.raise_for_status()
        body = response.json()
        row_results = {item["source_index"]: item for item in body["results"]}
        rejected = {item["source_index"]: item for item in body["errors"]}
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for row in batch:
            index = row["source_index"]
            if index in rejected:
                item = rejected[index]
                results[index] = (timestamp, item["status"],
                                  item.get("action", "rejected"), item["message"])
            else:
                item = row_results[index]
                fallback = "inserted" if item["status"] == 200 else "unchanged"
                results[index] = (timestamp, item["status"],
                                  item.get("action", fallback), item["message"])
        checkpoint()

    return result_frame(results).reindex(range(len(dataframe)))


def result_frame(results: dict[int, tuple[str, int, str, str]]) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_api": {index: value[0] for index, value in results.items()},
        "status_api": {index: value[1] for index, value in results.items()},
        "action_api": {index: value[2] for index, value in results.items()},
        "message_api": {index: value[3] for index, value in results.items()},
    }).sort_index()
