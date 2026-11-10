#!/usr/bin/env python3
"""Audit a refinement sample manifest with per-file resumable records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from audit_refinement_pairs import (
    MEASUREMENTS,
    estimate_ready,
    read_csv,
    row_characteristics,
    source_row_id,
)


def normalized_status(value: str | None) -> str:
    try:
        return str(int(float(value or "")))
    except ValueError:
        return value or ""


def record_path(records_dir: Path, log_rel: str) -> Path:
    safe_name = log_rel.replace("/", "__")
    return records_dir / f"{safe_name}.json"


def audit_log(data_root: Path, log_rel: str) -> dict[str, object]:
    crawler_root = data_root / "crawler"
    log_path = crawler_root / log_rel
    refinement_rel = Path(str(log_rel).replace("_log.csv.gz", ".csv.gz"))
    original_rel = Path(str(refinement_rel).replace("_betterestimate.csv.gz", ".csv.gz"))
    refinement_path = data_root / refinement_rel
    original_path = data_root / original_rel
    if not refinement_path.is_file() or not original_path.is_file():
        return {
            "audit_version": 3,
            "log": log_rel,
            "original": str(original_rel),
            "refinement": str(refinement_rel),
            "status": "source_pair_missing",
            "missing": [str(path) for path in (original_path, refinement_path) if not path.is_file()],
        }
    results, refinements, originals = map(read_csv, (log_path, refinement_path, original_path))
    status_counts = Counter(normalized_status(row.get("status_api")) for row in results)
    conflicts = []
    for result in results:
        if normalized_status(result.get("status_api")) != "409":
            continue
        try:
            index = int(result.get("", ""))
            original, refinement = originals[index], refinements[index]
        except (ValueError, IndexError):
            conflicts.append({"row_index": result.get(""), "pairing": "unavailable"})
            continue
        conflicts.append({
            "row_index": index,
            "row_id": source_row_id(refinement),
            "row_id_matches_position": source_row_id(original) == source_row_id(refinement),
            # A 409 proves endpoint validation reached INSERT ... ON CONFLICT.
            # estimate_ready determines whether valid=true was routed to the
            # valid platform table rather than its _invalid counterpart.
            "eligible_valid_conflict": estimate_ready(refinement),
            "characteristics": sorted(row_characteristics(original, refinement)),
            "original": {field: original.get(field) for field in MEASUREMENTS},
            "refinement": {field: refinement.get(field) for field in MEASUREMENTS},
        })
    return {
        "audit_version": 3,
        "log": log_rel,
        "original": str(original_rel),
        "refinement": str(refinement_rel),
        "status_counts": status_counts,
        "conflicts": conflicts,
    }


def safe_audit_log(data_root: Path, log_rel: str) -> dict[str, object]:
    try:
        return audit_log(data_root, log_rel)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        return {
            "audit_version": 3,
            "log": log_rel,
            "status": "unreadable",
            "error": str(error),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("records_dir", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.records_dir.mkdir(parents=True, exist_ok=True)
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")

    pending = []
    for log_rel in manifest["selected_logs"]:
        output = record_path(args.records_dir, log_rel)
        if output.exists():
            existing = json.loads(output.read_text(encoding="utf-8"))
            if existing.get("audit_version") == 3:
                continue
        pending.append(log_rel)

    written = 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        records = executor.map(safe_audit_log, [args.data_root] * len(pending), pending)
        for log_rel, record in zip(pending, records):
            output = record_path(args.records_dir, log_rel)
            temporary = output.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            temporary.replace(output)
            written += 1
    print(json.dumps({
        "manifest_records": len(manifest["selected_logs"]),
        "written_records": written,
        "records_dir": str(args.records_dir),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
