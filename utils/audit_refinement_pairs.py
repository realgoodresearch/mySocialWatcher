#!/usr/bin/env python3
"""Read-only audit of better-estimate source files and crawler results.

The utility pairs a refinement file with the source file that shares its name
without ``_betterestimate``.  It deliberately treats the filename as file
provenance, not as evidence that every row in that file was refined.
"""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


MEASUREMENTS = (
    "mau_audience",
    "mau_audience_lower_bound",
    "mau_audience_upper_bound",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def usable(value: float | None) -> bool:
    return value is not None and value >= 0


def row_id(value: str | None) -> str | None:
    numeric = number(value)
    if numeric is None:
        return value
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def source_row_id(row: dict[str, str]) -> str | None:
    """Support both legacy blank and current ``row_id`` CSV headers."""
    return row_id(row.get("row_id", row.get("")))


def refined_flag(row: dict[str, str]) -> bool:
    try:
        return ("better_estimates", True) in ast.literal_eval(row["all_fields"])
    except (KeyError, SyntaxError, ValueError):
        return False


def parse_response(value: str):
    """Parse response representations accepted from historical crawler CSVs."""
    if value.startswith(("b'", 'b"')):
        return json.loads(ast.literal_eval(value).decode("utf-8"))
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return ast.literal_eval(value)


def estimate_ready(row: dict[str, str]) -> bool:
    """Apply the write endpoint's Meta-validity check to a crawler row."""
    try:
        response = parse_response(row["response"])
        items = [response] if isinstance(response, dict) else response
        return bool(items) and all(bool(item["data"][0]["estimate_ready"]) for item in items)
    except (KeyError, IndexError, TypeError, ValueError, SyntaxError, json.JSONDecodeError):
        return False


def row_characteristics(original: dict[str, str], refinement: dict[str, str]) -> set[str]:
    characteristics: set[str] = set()
    if refined_flag(refinement):
        characteristics.add("better_estimates_flag")
    changed = any(original.get(field) != refinement.get(field) for field in MEASUREMENTS)
    if changed:
        characteristics.add("measurement_changed")
    if any(
        usable(number(original.get(field))) and not usable(number(refinement.get(field)))
        for field in MEASUREMENTS
    ):
        characteristics.add("usable_measurement_lost")
    lower = number(refinement.get("mau_audience_lower_bound"))
    upper = number(refinement.get("mau_audience_upper_bound"))
    if usable(lower) and usable(upper) and lower > upper:
        characteristics.add("inverted_bounds")
    if any(number(refinement.get(field)) == 0 for field in MEASUREMENTS):
        characteristics.add("zero_measurement")
    if any(number(refinement.get(field)) is not None and number(refinement.get(field)) < 0
           for field in MEASUREMENTS):
        characteristics.add("negative_measurement")
    return characteristics


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--modified-after", type=parse_time)
    parser.add_argument("--limit-files", type=int)
    parser.add_argument("--examples", type=int, default=10)
    args = parser.parse_args()

    crawler_root = args.data_root / "crawler"
    logs = sorted(crawler_root.rglob("*_betterestimate_log.csv.gz"))
    if args.modified_after:
        logs = [path for path in logs if datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc) >= args.modified_after]
    if args.limit_files is not None:
        logs = logs[:args.limit_files]

    counts: Counter[str] = Counter()
    examples: list[dict[str, object]] = []
    for log_path in logs:
        rel = log_path.relative_to(crawler_root)
        refinement_rel = Path(str(rel).replace("_log.csv.gz", ".csv.gz"))
        original_rel = Path(str(refinement_rel).replace("_betterestimate.csv.gz", ".csv.gz"))
        refinement_path = args.data_root / refinement_rel
        original_path = args.data_root / original_rel
        if not refinement_path.is_file() or not original_path.is_file():
            counts["unpaired_file"] += 1
            continue
        try:
            results, refinements, originals = map(read_csv, (log_path, refinement_path, original_path))
        except (OSError, csv.Error, UnicodeDecodeError):
            counts["unreadable_file"] += 1
            continue
        for result in results:
            if result.get("status_api") != "409":
                continue
            counts["conflict_rows"] += 1
            try:
                position = int(result.get("", ""))
                original, refinement = originals[position], refinements[position]
            except (ValueError, IndexError):
                counts["unpaired_row"] += 1
                continue
            if source_row_id(original) == source_row_id(refinement):
                counts["position_and_row_id_match"] += 1
            else:
                counts["position_row_id_mismatch"] += 1
            characteristics = row_characteristics(original, refinement)
            counts.update(characteristics)
            if len(examples) < args.examples:
                examples.append({
                    "source": str(refinement_rel),
                    "row_index": position,
                    "row_id": refinement.get("row_id"),
                    "name": refinement.get("name"),
                    "timestamp": refinement.get("timestamp"),
                    "platforms": refinement.get("publisher_platforms"),
                    "characteristics": sorted(characteristics),
                    "original": {field: original.get(field) for field in MEASUREMENTS},
                    "refinement": {field: refinement.get(field) for field in MEASUREMENTS},
                })
    print(json.dumps({"files_considered": len(logs), "counts": counts, "examples": examples}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
