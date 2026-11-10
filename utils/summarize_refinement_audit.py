#!/usr/bin/env python3
"""Print aggregate counts from resumable refinement-audit records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_dir", type=Path)
    args = parser.parse_args()
    files = sorted(args.records_dir.glob("*.json"))
    record_statuses: Counter[str] = Counter()
    crawler_statuses: Counter[str] = Counter()
    characteristics: Counter[str] = Counter()
    pairing: Counter[str] = Counter()
    conflicts = 0
    eligibility: Counter[str] = Counter()
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        record_statuses[record.get("status", "audited")] += 1
        crawler_statuses.update(record.get("status_counts", {}))
        for conflict in record.get("conflicts", []):
            conflicts += 1
            eligibility["eligible_valid_conflict" if conflict.get("eligible_valid_conflict")
                        else "excluded_not_estimate_ready"] += 1
            pairing["position_and_row_id_match" if conflict.get("row_id_matches_position")
                    else "position_row_id_mismatch"] += 1
            characteristics.update(conflict.get("characteristics", []))
    print(json.dumps({
        "record_count": len(files),
        "record_statuses": record_statuses,
        "crawler_statuses": crawler_statuses,
        "conflict_rows": conflicts,
        "eligibility": eligibility,
        "pairing": pairing,
        "characteristics": characteristics,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
