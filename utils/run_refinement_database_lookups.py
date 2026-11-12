#!/usr/bin/env python3
"""Read-only database comparisons for a refinement lookup manifest."""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def csv_row(path: Path, index: int) -> dict[str, str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for position, row in enumerate(csv.DictReader(stream)):
            if position == index:
                return row
    raise IndexError(index)


def parse_response(value: str):
    if value.startswith(("b'", 'b"')):
        return json.loads(ast.literal_eval(value).decode("utf-8"))
    if value.startswith("{"):
        return json.loads(value)
    return ast.literal_eval(value)


def number(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def country_from_geo(geo: dict) -> str:
    countries: set[str] = set()
    if geo.get("name") == "countries":
        countries.update(value for value in geo.get("values", []) if isinstance(value, str))
    reference = geo.get("pySocialWatcherReference")
    if isinstance(reference, str):
        for component in reference.split("; "):
            key, separator, value = component.partition(":")
            if separator and key in {"country", "country_code"}:
                countries.add(value)
    elif isinstance(reference, dict):
        countries.update(reference[key] for key in ("country", "country_code")
                         if isinstance(reference.get(key), str))
    for value in geo.get("values", []):
        if isinstance(value, dict):
            countries.update(candidate for key, candidate in value.items()
                             if "country" in key and isinstance(candidate, str)
                             and len(candidate) == 2)
    countries.update(candidate for key, candidate in geo.items()
                     if "country" in key and isinstance(candidate, str)
                     and len(candidate) == 2)
    normalized = {country.upper() for country in countries if len(country) == 2}
    if len(normalized) != 1 or "XX" in normalized:
        raise ValueError("geo_locations does not identify exactly one valid ISO-2 country")
    return normalized.pop()


def expected_row(row: dict[str, str], log: str) -> dict:
    all_fields = dict(ast.literal_eval(row["all_fields"]))
    geo = all_fields["geo_locations"]
    platform = ast.literal_eval(row["publisher_platforms"])[0]
    ages = ast.literal_eval(row["ages_ranges"])
    age_min = ages["min"] if isinstance(ages, dict) else ages[0]
    age_max = ages.get("max", 999) if isinstance(ages, dict) else ages[1]
    if age_max is None:
        age_max = 999
    country = country_from_geo(geo)
    timestamp = number(row["timestamp"])
    date = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
    return {
        "platform": platform,
        "collection": Path(log).parts[-3].strip("_"),
        "country": country,
        "collection_date": date,
        "timestamp": timestamp,
        "gender": number(row["genders"]),
        "age_min": number(str(age_min)),
        "age_max": number(str(age_max)),
        "dau": number(row["dau_audience"]),
        "geo_locations": geo,
        "targeting": ast.literal_eval(row["targeting"]) or {},
        "response": parse_response(row["response"]),
    }


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def lookup_sql(expected: dict) -> str:
    table = expected["platform"]
    columns = (
        "collection_id, timestamp, collection_date, country, gender, age_min, age_max, dau, "
        "mau, mau_lower, mau_upper, geo_locations, targeting, response, "
        "all_fields ? 'better_estimates' AS marked_refinement"
    )
    predicate = (
        f"country = {sql_string(expected['country'])} "
        f"AND collection_id = (SELECT id FROM collections WHERE name = {sql_string(expected['collection'])}) "
        f"AND timestamp = {expected['timestamp']}"
    )
    return (
        "SELECT row_to_json(candidate)::text FROM "
        f"(SELECT {columns} FROM {table} WHERE {predicate}) AS candidate;"
    )


IDENTITY_FIELDS = (
    "country", "collection_date", "gender", "age_min", "age_max", "dau",
    "geo_locations", "targeting", "response",
)


def comparable(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return str(value) if isinstance(value, datetime) else value


def identity_differences(expected: dict, candidate: dict) -> list[str]:
    return [field for field in IDENTITY_FIELDS
            if comparable(expected[field]) != comparable(candidate[field])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("records_dir", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    args.records_dir.mkdir(parents=True, exist_ok=True)
    lookups = json.loads(args.manifest.read_text(encoding="utf-8"))["lookups"]
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    def process(lookup: dict) -> bool:
        key = f"{Path(lookup['log']).name}.{lookup['row_index']}.json"
        output = args.records_dir / key
        if output.exists():
            existing = json.loads(output.read_text(encoding="utf-8"))
            if existing.get("lookup_version") == 5:
                return False
        source = args.data_root / str(lookup["log"]).replace("_log.csv.gz", ".csv.gz")
        try:
            expected = expected_row(csv_row(source, int(lookup["row_index"])), lookup["log"])
            sql = lookup_sql(expected)
            result = subprocess.run(
                ["docker", "exec", "datahub_db", "psql", "-X", "-U", "postgres", "-d",
                 "social_media_audience", "-At", "-F", "\t", "-c", sql],
                check=True, text=True, capture_output=True,
            )
            candidates = [json.loads(line) for line in result.stdout.splitlines() if line]
            comparisons = [
                {"candidate": candidate,
                 "identity_differences": identity_differences(expected, candidate)}
                for candidate in candidates
            ]
            record = {
                "lookup_version": 5,
                "lookup": lookup,
                "expected": expected,
                "candidates": comparisons,
            }
        except subprocess.CalledProcessError as error:
            record = {
                "lookup_version": 5,
                "lookup": lookup,
                "error": str(error),
                "stderr": error.stderr.strip(),
            }
        except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as error:
            record = {"lookup_version": 5, "lookup": lookup, "error": str(error)}
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)
        return True

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        written = sum(executor.map(process, lookups))
    print(json.dumps({
        "lookups": len(lookups),
        "written_records": written,
        "records_dir": str(args.records_dir),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
