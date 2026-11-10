#!/usr/bin/env python3
"""Copy a stratified audit sample into isolated crawler test directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


TARGETS = tuple(
    (year, trait)
    for year in ("2024", "2025", "2026")
    for trait in ("ordinary", "zero_measurement", "inverted_bounds", "negative_measurement")
)
RISKS = {"zero_measurement", "inverted_bounds", "usable_measurement_lost", "negative_measurement"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def traits(conflict: dict) -> set[str]:
    result = set(conflict.get("characteristics", []))
    if "measurement_changed" in result and not result.intersection(RISKS):
        result.add("ordinary")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("records_dir", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    if args.output_root.exists():
        parser.error("output root must not already exist")

    candidates = []
    for path in sorted(args.records_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        eligible = [item for item in record.get("conflicts", [])
                    if item.get("eligible_valid_conflict")]
        if not eligible:
            continue
        combined = set().union(*(traits(item) for item in eligible))
        candidates.append((record, combined))

    selected = []
    used_logs = set()
    for year, trait in TARGETS:
        choice = next((item for item in candidates
                       if item[0]["log"] not in used_logs
                       and year in item[0]["log"] and trait in item[1]), None)
        if choice is None:
            continue
        selected.append((year, trait, *choice))
        used_logs.add(choice[0]["log"])

    originals_root = args.output_root / "originals"
    refinements_root = args.output_root / "refinements"
    reference_root = args.output_root / "reference_logs"
    files = []
    for year, trait, record, characteristics in selected:
        for kind, relative, destination_root in (
            ("original", record["original"], originals_root),
            ("refinement", record["refinement"], refinements_root),
            ("reference_log", record["log"], reference_root),
        ):
            source_root = args.data_root / "crawler" if kind == "reference_log" else args.data_root
            source = source_root / relative
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files.append({
                "kind": kind,
                "source": str(source),
                "destination": str(destination),
                "size": source.stat().st_size,
                "mtime_ns": source.stat().st_mtime_ns,
                "sha256": digest(source),
            })
        record_conflicts = [item for item in record["conflicts"]
                            if item.get("eligible_valid_conflict")]
        record["selected_stratum"] = {"year": year, "trait": trait}
        record["eligible_conflict_count"] = len(record_conflicts)
        record["observed_characteristics"] = sorted(characteristics)

    manifest = {
        "selection": "one eligible audited file for each available year/condition stratum",
        "selected_file_pairs": len(selected),
        "records": [record for _, _, record, _ in selected],
        "files": files,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "selected_file_pairs": len(selected),
        "strata": [record["selected_stratum"] for record in manifest["records"]],
        "output_root": str(args.output_root),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
