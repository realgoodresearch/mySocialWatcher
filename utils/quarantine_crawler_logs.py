#!/usr/bin/env python3
"""Preview or quarantine failed or corrupt logs so their inputs can be crawled again.

Stop all crawlers before using --move. Only *_log.csv.gz files are considered;
source data and temporary/error markers are never moved. Quarantine must be
outside the data directory so the crawler cannot mistake archived logs for input.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zlib


def failed_statuses(path, ignore_statuses=None):
    """Return non-2xx/non-409 status counts; reject incomplete or malformed logs."""
    failures = Counter()
    rows = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "status_api" not in reader.fieldnames:
            raise ValueError("missing status_api column")
        for row in reader:
            rows += 1
            value = row.get("status_api")
            try:
                status = Decimal(value.strip())
                if not status.is_finite() or status != status.to_integral_value():
                    raise ValueError
                status = int(status)
                if not 100 <= status <= 599:
                    raise ValueError
            except (AttributeError, InvalidOperation, ValueError):
                raise ValueError(f"invalid status_api on data row {rows}: {value!r}") from None
            if not (200 <= status < 300 or status == 409) and status not in (ignore_statuses or ()):
                failures[status] += 1
    if not rows:
        raise ValueError("no response rows")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crawler_dir", type=Path, help="crawler output directory, e.g. ./data/crawler")
    parser.add_argument("--move", action="store_true", help="move failed or corrupt logs; stop all crawlers first (default: preview)")
    parser.add_argument("--limit", type=int, help="stop after this many failed or corrupt logs, newest first (default: unlimited)")
    parser.add_argument("--ignore-status", type=int, nargs='+', help="ignore these HTTP statuses (e.g. --ignore-status 400 401); corrupt logs still qualify")
    parser.add_argument("--max-age-days", type=int, help="only inspect logs modified within this many days")
    parser.add_argument("--quarantine-dir", type=Path, help="archive directory outside data/ (default: crawler-recovery/log-quarantine)")
    args = parser.parse_args(argv)
    if args.max_age_days is not None and args.max_age_days < 1:
        parser.error("--max-age-days must be a positive integer")
    if args.ignore_status and any(status < 100 or status > 599 for status in args.ignore_status):
        parser.error("--ignore-status must contain HTTP status codes (100-599)")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    root = args.crawler_dir.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    archive = (args.quarantine_dir or root.parent.parent / "crawler-recovery" / "log-quarantine").resolve()
    if archive == root.parent or root.parent in archive.parents:
        parser.error("quarantine directory must be outside the crawler's parent data directory")

    scanned = selected = blocked = invalid = corrupt = moved = 0
    batch = None
    # Sort by modification time, using the path to break ties consistently.
    paths = sorted(root.rglob("*_log.csv.gz"), key=lambda path: (-path.lstat().st_mtime_ns, str(path)))
    cutoff = time.time() - args.max_age_days * 86400 if args.max_age_days else None
    for path in paths:
        if cutoff is not None and path.lstat().st_mtime < cutoff:
            continue
        scanned += 1
        relative = path.relative_to(root)
        # Symlinks must not allow moves outside the selected output tree.
        if path.is_symlink() or root not in path.resolve().parents:
            print(f"SKIP {relative}: symlink or outside crawler directory", file=sys.stderr)
            invalid += 1
            continue
        prefix = path.name.removesuffix("_log.csv.gz")
        markers = [path.with_name(prefix + suffix) for suffix in ("_temp.txt", "_error.txt")]
        if any(marker.exists() for marker in markers):
            print(f"BLOCKED {relative}: temporary/error marker exists; left unchanged")
            blocked += 1
            continue
        try:
            failures = failed_statuses(path, args.ignore_status)
        except (gzip.BadGzipFile, EOFError, zlib.error, UnicodeError, csv.Error, ValueError) as exc:
            corrupt += 1
            statuses = f"CORRUPT: {exc}"
        except OSError as exc:
            print(f"UNREADABLE {relative}: {exc}; left unchanged", file=sys.stderr)
            invalid += 1
            continue
        else:
            if not failures:
                continue
            statuses = ", ".join(f"{status}: {count}" for status, count in sorted(failures.items()))
        selected += 1
        print(f"{'MOVE' if args.move else 'WOULD MOVE'} {relative} [{statuses}]")
        if args.move:
            if batch is None:
                archive.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
                batch = Path(tempfile.mkdtemp(prefix=stamp, dir=archive))
            destination = batch / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Unique run directory and preserved relative paths avoid overwrites.
            shutil.move(str(path), str(destination))
            moved += 1
        if args.limit is not None and selected >= args.limit:
            print(f"Reached limit of {args.limit} failed or corrupt logs; stopping.")
            break

    print(f"Scanned {scanned}; selected {selected} (corrupt {corrupt}); moved {moved}; blocked {blocked}; unreadable/skipped {invalid}.")
    if batch:
        print(f"Quarantine: {batch}")
    if not args.move:
        print("Preview only. Stop all crawlers, then repeat with --move to requeue these files.")
    return 1 if invalid or blocked else 0


if __name__ == "__main__":
    sys.exit(main())
