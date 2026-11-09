#!/usr/bin/env python3
"""Classify stored measurements from refinement database lookup records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


FIELDS = ("mau_audience", "mau_audience_lower_bound", "mau_audience_upper_bound")


def value(raw: str | None):
    if raw is None or raw == "":
        return None
    return float(raw)


def measurement(row: dict[str, str]) -> tuple:
    return tuple(value(row.get(field)) for field in FIELDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_dir", type=Path)
    args = parser.parse_args()
    counts: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    details: list[dict] = []
    for path in sorted(args.records_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        lookup = record["lookup"]
        if "error" in record:
            category = "query_error"
        elif not record.get("candidates"):
            category = "collection_timestamp_missing"
        else:
            category = None
            exact = [item["candidate"] for item in record["candidates"]
                     if not item["identity_differences"]]
            if not exact:
                category = "identity_mismatch"
                stored = None
            elif len(exact) > 1:
                category = "multiple_exact_matches"
                stored = None
            else:
                candidate = exact[0]
                stored = tuple(value(candidate[field])
                               for field in ("mau", "mau_lower", "mau_upper"))
            original = measurement(lookup["original"])
            refinement = measurement(lookup["refinement"])
            if category in {"identity_mismatch", "multiple_exact_matches"}:
                pass
            elif stored == original == refinement:
                category = "equivalent"
            elif stored == original:
                category = "original_retained"
            elif stored == refinement:
                category = "refinement_retained"
            else:
                category = "unexpected_stored_measurement"
        counts[category] += 1
        examples.setdefault(category, {"log": lookup["log"], "row_index": lookup["row_index"]})
        details.append({
            "category": category,
            "log": lookup["log"],
            "row_index": lookup["row_index"],
            "characteristics": lookup.get("characteristics", []),
            "candidates": record.get("candidates", []),
        })
    print(json.dumps({"counts": counts, "examples": examples, "details": details}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
