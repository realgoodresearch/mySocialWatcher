#!/usr/bin/env python3
"""Create a reproducible monthly sample manifest for refinement-log auditing."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DATE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")


def collection_date(path: Path) -> str | None:
    matches = DATE.findall(path.name)
    return matches[-1] if matches else None


def balanced_sample(logs: list[str], limit: int) -> list[str]:
    """Select paths round-robin by collection directory."""
    groups: dict[str, list[str]] = defaultdict(list)
    for log in logs:
        groups[str(Path(log).parent)].append(log)
    for paths in groups.values():
        paths.sort()
    selected: list[str] = []
    while len(selected) < limit:
        added = False
        for directory in sorted(groups):
            if groups[directory] and len(selected) < limit:
                selected.append(groups[directory].pop(0))
                added = True
        if not added:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-files-per-date", type=int, default=50)
    args = parser.parse_args()

    crawler_root = args.data_root / "crawler"
    by_month: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for path in crawler_root.rglob("*_betterestimate_log.csv.gz"):
        date = collection_date(path)
        if date:
            by_month[date[:6]][date].append(str(path.relative_to(crawler_root)))

    strata = []
    selected_logs = []
    for month, dates in sorted(by_month.items()):
        selected_date = min(dates, key=lambda date: (abs(int(date[6:]) - 15), date))
        available_logs = sorted(dates[selected_date])
        logs = balanced_sample(available_logs, args.max_files_per_date)
        strata.append({
            "month": month,
            "selected_date": selected_date,
            "available_dates": len(dates),
            "available_log_count": len(available_logs),
            "selected_log_count": len(logs),
        })
        selected_logs.extend(logs)

    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(args.data_root),
        "selection": "one available date nearest the 15th of each calendar month; "
                     "paths selected round-robin by collection directory",
        "max_files_per_date": args.max_files_per_date,
        "strata": strata,
        "selected_logs": selected_logs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "months": len(strata),
        "selected_logs": len(selected_logs),
        "first": strata[0] if strata else None,
        "last": strata[-1] if strata else None,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
