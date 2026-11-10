#!/usr/bin/env python3
"""Create a small, reproducible lookup sample from audit conflict records."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


DATE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
POLICY_RISKS = {"inverted_bounds", "usable_measurement_lost", "zero_measurement"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-month", type=int, default=2)
    args = parser.parse_args()

    by_month: dict[str, list[dict[str, object]]] = defaultdict(list)
    for path in sorted(args.records_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        matches = DATE.findall(record["log"])
        if not matches:
            continue
        for conflict in record.get("conflicts", []):
            if not conflict.get("eligible_valid_conflict", False):
                continue
            entry = {"log": record["log"], **conflict}
            by_month[matches[-1][:6]].append(entry)

    selected = []
    for month, conflicts in sorted(by_month.items()):
        ordinary = sorted(
            (entry for entry in conflicts
             if "measurement_changed" in entry.get("characteristics", [])
             and not POLICY_RISKS.intersection(entry.get("characteristics", []))),
            key=lambda entry: (entry["log"], entry["row_index"]),
        )
        risky = sorted(
            (entry for entry in conflicts
             if POLICY_RISKS.intersection(entry.get("characteristics", []))),
            key=lambda entry: (entry["log"], entry["row_index"]),
        )
        choices = []
        if ordinary:
            choices.append(ordinary[0])
        if risky and len(choices) < args.per_month:
            choices.append(risky[0])
        for entry in sorted(conflicts, key=lambda item: (item["log"], item["row_index"])):
            if len(choices) >= args.per_month:
                break
            if entry not in choices:
                choices.append(entry)
        selected.extend(choices)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "version": 2,
        "selection": "eligible valid-table conflicts; one ordinary changed and one policy-risk example per month when available",
        "lookups": selected,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"months": len(by_month), "lookups": len(selected), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
