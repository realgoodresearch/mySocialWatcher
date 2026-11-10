#!/usr/bin/env python3
"""Check isolated crawler results against provenance-aware conflict policy."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mysocialwatcher.crawler.batch import dataframe_to_v2_rows


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def country(geo: dict) -> str:
    values = {value.upper() for value in geo.get("values", []) if isinstance(value, str)}
    for value in geo.get("values", []):
        if isinstance(value, dict):
            values.update(candidate.upper() for key, candidate in value.items()
                          if "country" in key and isinstance(candidate, str)
                          and len(candidate) == 2)
    values.update(candidate.upper() for key, candidate in geo.items()
                  if "country" in key and isinstance(candidate, str) and len(candidate) == 2)
    if len(values) != 1:
        raise ValueError("could not determine one country")
    return values.pop()


def identity(row: dict) -> tuple:
    return (
        country(row["geo_locations"]),
        datetime.fromtimestamp(row["timestamp"], timezone.utc).date().isoformat(),
        row["gender"], row["age_min"], row.get("age_max", 999), row["dau"],
        canonical(row["geo_locations"]), canonical(row.get("targeting") or {}),
        canonical(row["response"]),
    )


def estimate_ready(row: dict) -> bool:
    response = row["response"]
    items = [response] if isinstance(response, dict) else response
    return bool(items) and all(bool(item["data"][0]["estimate_ready"]) for item in items)


def outcomes(path: Path) -> dict[int, tuple[int, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return {position: (int(float(row["status_api"])), row["action_api"])
                for position, row in enumerate(csv.DictReader(stream))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("originals_root", type=Path)
    parser.add_argument("refinements_root", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    mismatches = []
    for record in manifest["records"]:
        original_path = args.originals_root / record["original"]
        refinement_path = args.refinements_root / record["refinement"]
        log_path = (args.refinements_root / "crawler" /
                    str(record["refinement"]).replace(".csv.gz", "_log.csv.gz"))
        original_rows, original_errors = dataframe_to_v2_rows(pd.read_csv(original_path))
        refined_rows, refined_errors = dataframe_to_v2_rows(pd.read_csv(refinement_path))
        original_by_index = {row["source_index"]: row for row in original_rows}
        refined_by_index = {row["source_index"]: row for row in refined_rows}
        actual = outcomes(log_path)
        counts["client_errors"] += len(original_errors) + len(refined_errors)
        for index, refined in refined_by_index.items():
            original = original_by_index.get(index)
            if original is None or not estimate_ready(refined):
                continue
            if all(refined.get(field) is None
                   for field in ("mau", "mau_lower", "mau_upper")):
                counts["expected_endpoint_rejection"] += 1
                status, action = actual.get(index, (None, None))
                counts[f"expected_endpoint_rejection_status_{status}"] += 1
                counts[f"expected_endpoint_rejection_action_{action}"] += 1
                if (status, action) != (400, "rejected"):
                    mismatches.append({
                        "file": record["refinement"], "row_index": index,
                        "category": "expected_endpoint_rejection",
                        "expected": [400, "rejected"], "actual": [status, action],
                    })
                continue
            source_marked = refined.get("all_fields", {}).get("better_estimates") is True
            counts["source_marked" if source_marked else "legacy_marker_inferred"] += 1
            # Every input in refinements_root came from a _betterestimate file;
            # the real crawler adds provenance before submitting legacy files.
            marked = True
            same_identity = identity(original) == identity(refined)
            if same_identity and marked:
                expected, expected_action, category = 200, "promoted", "expected_promotion"
            elif same_identity:
                expected, expected_action, category = 409, "unchanged", "expected_unmarked_conflict"
            else:
                expected, expected_action, category = 200, "inserted", "expected_distinct_insert"
            counts[category] += 1
            status, action = actual.get(index, (None, None))
            counts[f"{category}_status_{status}"] += 1
            counts[f"{category}_action_{action}"] += 1
            if (status, action) != (expected, expected_action):
                mismatches.append({
                    "file": record["refinement"], "row_index": index,
                    "category": category,
                    "expected": [expected, expected_action],
                    "actual": [status, action],
                })

    print(json.dumps({"counts": counts, "mismatches": mismatches[:20]}, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
