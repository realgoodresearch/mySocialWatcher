#!/usr/bin/env python3
"""Archive source/log pairs whose crawler rows are complete and acceptable.

CURRENTLY DISABLED: A data sync from remote collectors after running this utility
would re-sync a bunch of data needlessly. The main() function is commented out below
to disable the utility until we are ready to use it.

Preview is the default. With --move, both files are copied and SHA-256 verified
in cold storage before either hot copy is removed. Relative paths are retained
under COLD_STORAGE/data and COLD_STORAGE/data/crawler.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zlib

csv.field_size_limit(sys.maxsize)


def integer(value):
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid integer: {value!r}") from None


def utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except (AttributeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"invalid date/time {value!r}; use YYYY-MM-DD or ISO 8601"
        ) from None


def acceptable_missing_mau(message):
    lower = (message or "").lower()
    return "at least one of these arguments are required" in lower and all(
        field in lower for field in ("mau", "mau_lower", "mau_upper")
    )


def load_recovered(path):
    recovered = set()
    if not path.is_file():
        return recovered
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                source = Path(record["source"])
                index = integer(record["row_index"])
                status = integer(record["retry_status"])
                if (
                    source.is_absolute()
                    or ".." in source.parts
                    or index < 0
                    or not (200 <= status < 300 or status == 409)
                ):
                    raise ValueError
            except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid recovery ledger line {line_number}") from exc
            recovered.add((source.as_posix(), index))
    return recovered


def inspect_log(path, source_key, recovered, extra_400_messages):
    counts = Counter()
    recovered_count = 0
    rows = 0
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames.count("status_api") != 1:
            raise ValueError("expected one status_api column")
        for row in reader:
            if not row:
                continue
            if "" not in row or integer(row[""]) != rows:
                raise ValueError(
                    "log indices must be ordered positions starting at zero"
                )
            status = integer(row["status_api"])
            if not 100 <= status <= 599:
                raise ValueError(f"invalid HTTP status {status}")
            counts[status] += 1
            acceptable = status in (200, 409)
            if status == 400:
                message = row.get("message_api", "")
                acceptable = acceptable_missing_mau(message) or any(
                    text in message for text in extra_400_messages
                )
            if not acceptable and (source_key, rows) in recovered:
                acceptable = True
                recovered_count += 1
            if not acceptable:
                return False, rows + 1, counts, recovered_count
            rows += 1
    if rows == 0:
        raise ValueError("empty response log")
    return True, rows, counts, recovered_count


def source_rows(path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, [])
        if not header:
            raise ValueError("source has no CSV header")
        rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(f"source row {rows} does not match header width")
            rows += 1
    return rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if (
            destination.is_file()
            and source.stat().st_size == destination.stat().st_size
        ):
            source_hash = sha256(source)
            if source_hash == sha256(destination):
                return source_hash
        raise FileExistsError(f"cold-storage collision: {destination}")
    fd, temporary_name = tempfile.mkstemp(prefix=".archive-", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        source_hash = sha256(source)
        if source_hash != sha256(temporary):
            raise OSError(f"checksum verification failed: {source}")
        os.replace(temporary, destination)
        return source_hash
    finally:
        temporary.unlink(missing_ok=True)


def append_manifest(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="hot data root, e.g. data")
    parser.add_argument("cold_storage", type=Path, help="cold-storage root")
    parser.add_argument(
        "--move",
        action="store_true",
        help="copy, verify, manifest, then remove hot files (default: preview)",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        help="recovery ledger (default: crawler-recovery/retry-data/recovery-ledger.jsonl)",
    )
    parser.add_argument(
        "--accept-400-message",
        action="append",
        default=[],
        metavar="TEXT",
        help="also accept status 400 when message_api contains TEXT; repeat as needed",
    )
    parser.add_argument(
        "--limit", type=int, help="maximum source/log pairs, oldest first"
    )
    parser.add_argument(
        "--min-age-days", type=int, help="only archive logs at least this many days old"
    )
    parser.add_argument(
        "--modified-after",
        type=utc_timestamp,
        metavar="DATETIME",
        help="include logs modified at or after this UTC date/time",
    )
    parser.add_argument(
        "--modified-before",
        type=utc_timestamp,
        metavar="DATETIME",
        help="include logs modified before this UTC date/time",
    )
    args = parser.parse_args(argv)

    data = args.data_dir.resolve()
    logs = data / "crawler"
    cold = args.cold_storage.resolve()
    ledger = (
        args.ledger
        or data.parent / "crawler-recovery" / "retry-data" / "recovery-ledger.jsonl"
    ).resolve()
    if not data.is_dir() or not logs.is_dir():
        parser.error("data root and data/crawler must exist")
    if cold == data or cold in data.parents or data in cold.parents:
        parser.error("cold storage must be separate from the hot data directory")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.min_age_days is not None and args.min_age_days < 1:
        parser.error("--min-age-days must be positive")
    if any(not text for text in args.accept_400_message):
        parser.error("--accept-400-message cannot be empty")
    if (
        args.modified_after is not None
        and args.modified_before is not None
        and args.modified_after >= args.modified_before
    ):
        parser.error("--modified-after must be earlier than --modified-before")
    try:
        recovered = load_recovered(ledger)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    if args.move and not cold.is_dir():
        parser.error(
            "cold-storage root must already exist; verify that the drive is mounted"
        )

    cutoff = time.time() - args.min_age_days * 86400 if args.min_age_days else None
    paths = sorted(
        logs.rglob("*_log.csv.gz"),
        key=lambda path: (path.lstat().st_mtime_ns, str(path)),
    )
    scanned = eligible = moved = blocked = bytes_total = rows_total = (
        recovered_total
    ) = 0
    manifest = cold / "transfer-manifest.jsonl"
    for log in paths:
        modified = log.lstat().st_mtime
        if cutoff is not None and modified > cutoff:
            continue
        if args.modified_after is not None and modified < args.modified_after:
            continue
        if args.modified_before is not None and modified >= args.modified_before:
            continue
        scanned += 1
        relative_log = log.relative_to(logs)
        source_relative = relative_log.with_name(
            relative_log.name.removesuffix("_log.csv.gz") + ".csv.gz"
        )
        source = data / source_relative
        prefix = log.name.removesuffix("_log.csv.gz")
        markers = [
            log.with_name(prefix + suffix) for suffix in ("_temp.txt", "_error.txt")
        ]
        try:
            if (
                log.is_symlink()
                or source.is_symlink()
                or logs not in log.resolve().parents
                or data not in source.resolve().parents
            ):
                raise ValueError("symlink or path outside selected roots")
            if any(marker.exists() for marker in markers):
                raise ValueError("temporary/error marker exists")
            if not source.is_file():
                raise ValueError("corresponding source file is missing")
            acceptable, log_rows, counts, recovered_count = inspect_log(
                log, source_relative.as_posix(), recovered, args.accept_400_message
            )
            if not acceptable:
                continue
            if source_rows(source) != log_rows:
                raise ValueError("source/log row count mismatch")
        except (
            OSError,
            EOFError,
            gzip.BadGzipFile,
            zlib.error,
            UnicodeError,
            csv.Error,
            ValueError,
        ) as exc:
            blocked += 1
            print(f"SKIP {source_relative}: {exc}", file=sys.stderr)
            continue

        eligible += 1
        pair_bytes = source.stat().st_size + log.stat().st_size
        bytes_total += pair_bytes
        rows_total += log_rows
        recovered_total += recovered_count
        status_text = ", ".join(
            f"{status}:{count}" for status, count in sorted(counts.items())
        )
        print(
            f"{'ARCHIVE' if args.move else 'WOULD ARCHIVE'} {source_relative} "
            f"[{status_text}; ledger-recovered:{recovered_count}]"
        )
        if args.move:
            source_destination = cold / "data" / source_relative
            log_destination = cold / "data" / "crawler" / relative_log
            try:
                if shutil.disk_usage(cold).free < pair_bytes:
                    raise OSError("insufficient free space in cold storage")
                source_hash = stage_copy(source, source_destination)
                log_hash = stage_copy(log, log_destination)
                append_manifest(
                    manifest,
                    {
                        "archived_at": datetime.now(timezone.utc).isoformat(),
                        "source": source_relative.as_posix(),
                        "log": relative_log.as_posix(),
                        "source_bytes": source.stat().st_size,
                        "log_bytes": log.stat().st_size,
                        "source_sha256": source_hash,
                        "log_sha256": log_hash,
                        "rows": log_rows,
                        "status_counts": dict(counts),
                        "ledger_recovered_rows": recovered_count,
                    },
                )
                log.unlink()
                source.unlink()
                moved += 1
            except OSError as exc:
                blocked += 1
                print(
                    f"SKIP {source_relative}: transfer failed: {exc}", file=sys.stderr
                )
        if args.limit is not None and eligible >= args.limit:
            break

    print(
        f"Scanned {scanned}; eligible pairs {eligible}; moved pairs {moved}; "
        f"rows {rows_total}; ledger-recovered rows {recovered_total}; "
        f"bytes {bytes_total}; blocked/skipped {blocked}."
    )
    if not args.move:
        print("Preview only; stop crawlers and repeat with --move to transfer files.")
    elif moved:
        print(f"Manifest: {manifest}")
    return 1 if blocked else 0


if __name__ == "__main__":
    None
    # sys.exit(main())
