#!/usr/bin/env python3
"""Extract failed source rows without modifying original data or crawler logs.

Preview is the default. Use --write to create a separate retry dataset and a
manifest. Logs must come from unchanged source files: crawler log indices refer
to zero-based parsed row positions, NOT the source CSV's saved index column.
Stop crawlers/sync before using --write. Corrupt or incomplete live logs are
quarantined for full-file retry, regardless of status filters. Already archived corrupt
logs are left unchanged. Source-data errors are reported without moving logs.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path
import os
import shutil
import sys
import tempfile
import zlib

# Audience targeting and API error messages can exceed csv's small default.
csv.field_size_limit(sys.maxsize)


def integer(value):
    try:
        number = Decimal(value.strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (AttributeError, InvalidOperation, ValueError):
        raise ValueError(f"invalid integer: {value!r}") from None


def read_failures(path, statuses=None, ignore_statuses=None):
    selected = {}
    total = 0
    with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, [])
        if not header or header[0] != '' or header.count('status_api') != 1:
            raise ValueError('expected pandas row index in first column and one status_api column')
        status_column = header.index('status_api')
        for row in reader:
            if not row:
                continue
            if len(row) != len(header) or integer(row[0]) != total:
                raise ValueError('log indices must be complete, unique, ordered positions starting at zero')
            status = integer(row[status_column])
            if not 100 <= status <= 599:
                raise ValueError(f'invalid HTTP status {status}')
            if (not (200 <= status < 300 or status == 409)
                    and (statuses is None or status in statuses)
                    and status not in (ignore_statuses or ())):
                selected[total] = status
            total += 1
    if total == 0:
        raise ValueError('empty response log')
    return selected, total


def extract(source, selected, expected_rows, destination=None):
    """Validate row alignment, streaming selected rows to an optional new gzip."""
    temporary = None
    output = None
    try:
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.extract-', dir=destination.parent)
            os.close(fd)
            temporary = Path(name)
            output = gzip.open(temporary, 'wt', encoding='utf-8', newline='')
            writer = csv.writer(output)
        with gzip.open(source, 'rt', encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, [])
            if not header:
                raise ValueError('source has no CSV header')
            if output:
                writer.writerow(header)
            count = 0
            for row in reader:
                if not row:  # pandas read_csv skips blank lines
                    continue
                if len(row) != len(header):
                    raise ValueError(f'source row {count} does not match header width')
                if count in selected and output:
                    writer.writerow(row)
                count += 1
            if count != expected_rows:
                raise ValueError(f'source/log row count mismatch: {count} versus {expected_rows}')
        if output:
            output.close()
            output = None
            # A new batch owns this path; never overwrite an earlier extraction.
            if destination.exists():
                raise FileExistsError(destination)
            temporary.rename(destination)
            temporary = None
    finally:
        if output:
            output.close()
        if temporary:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data_dir', type=Path, help='original data root, e.g. ./data')
    parser.add_argument('--logs-dir', type=Path, help='mirrored log root (default: data_dir/crawler); may be one quarantine batch')
    parser.add_argument('--output-dir', type=Path, help='parent for new retry batches, outside data_dir')
    parser.add_argument('--quarantine-dir', type=Path, help='corrupt-log archive outside data/log/output roots')
    parser.add_argument('--write', action='store_true', help='write retry files and quarantine corrupt live logs; default is preview only')
    parser.add_argument('--limit', type=int, help='maximum selected files (row extractions plus corrupt logs), newest first')
    parser.add_argument('--status', type=int, nargs='+', help='only these error statuses, e.g. --status 500 502 503 504')
    parser.add_argument('--ignore-status', type=int, nargs='+', help='exclude these statuses; overrides --status (e.g. --ignore-status 400 401)')
    args = parser.parse_args(argv)
    data = args.data_dir.resolve()
    logs = (args.logs_dir or data / 'crawler').resolve()
    output = (args.output_dir or data.parent / 'crawler-retry-data').resolve()
    quarantine = (args.quarantine_dir or data.parent / 'crawler-log-quarantine').resolve()
    if not data.is_dir() or not logs.is_dir():
        parser.error('data and log roots must exist')
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.status and any(s < 300 or s > 599 or s == 409 for s in args.status):
        parser.error('--status must contain error statuses (300-599, excluding 409)')
    if args.ignore_status and any(s < 100 or s > 599 for s in args.ignore_status):
        parser.error('--ignore-status must contain HTTP status codes (100-599)')
    if any(output == root or root in output.parents for root in (data, logs)):
        parser.error('output must be outside both the original data and log roots')

    if any(quarantine == root or root in quarantine.parents or quarantine in root.parents
           for root in (data, output)) or quarantine == logs or logs in quarantine.parents:
        parser.error('quarantine must be separate from data, log, and retry-output roots')

    batch = quarantine_batch = None
    scanned = files = rows = skipped = corrupt = 0
    paths = sorted(logs.rglob('*_log.csv.gz'), key=lambda p: (-p.lstat().st_mtime_ns, str(p)))
    for log in paths:
        scanned += 1
        relative = log.relative_to(logs)
        source_relative = relative.with_name(relative.name.removesuffix('_log.csv.gz') + '.csv.gz')
        source = data / source_relative
        try:
            if log.is_symlink() or logs not in log.resolve().parents or data not in source.resolve().parents or source.is_symlink():
                raise ValueError('symlink or path outside selected roots')
            # Retain the collection/finished layout required by the crawler.
            if relative.parent.name != 'finished' or not source.name.startswith('dataframe_collected_finished_'):
                raise ValueError('unexpected crawler input layout')
            prefix = log.name.removesuffix('_log.csv.gz')
            # Check both archived and live markers if --logs-dir is a quarantine batch.
            for directory in (log.parent, (data / 'crawler' / relative).parent):
                if any((directory / (prefix + suffix)).exists() for suffix in ('_temp.txt', '_error.txt')):
                    raise ValueError('temporary/error marker exists; stop crawlers and resolve it first')
            if not source.is_file():
                raise ValueError('original source file is missing; cannot requeue it')
            try:
                selected, total = read_failures(log, args.status, args.ignore_status)
            except (gzip.BadGzipFile, EOFError, zlib.error, UnicodeError, csv.Error, ValueError) as exc:
                live_log = data / 'crawler' / relative
                if log.resolve() != live_log.resolve():
                    raise ValueError(f'corrupt log is already outside the live crawler directory; left unchanged: {exc}') from exc
                if args.write:
                    if quarantine_batch is None:
                        quarantine.mkdir(parents=True, exist_ok=True)
                        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
                        quarantine_batch = Path(tempfile.mkdtemp(prefix=stamp, dir=quarantine))
                    destination = quarantine_batch / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(log), str(destination))
                    with (quarantine_batch / 'manifest.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(dict(source=str(source), log=str(log),
                                                     quarantine=str(destination), reason=str(exc),
                                                     action='full-file retry')) + '\n')
                files += 1
                corrupt += 1
                print(f'{"QUARANTINED" if args.write else "WOULD QUARANTINE"} {relative}: {exc}; full-file retry')
                if args.limit and files >= args.limit:
                    break
                continue
            if not selected:
                continue
            if args.write and batch is None:
                output.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
                batch = Path(tempfile.mkdtemp(prefix=stamp, dir=output))
            extract(source, selected, total, batch / source_relative if batch else None)
        except (OSError, EOFError, zlib.error, UnicodeError, csv.Error, ValueError) as exc:
            skipped += 1
            print(f'SKIP {relative}: {exc}', file=sys.stderr)
            continue
        files += 1
        rows += len(selected)
        counts = dict(Counter(selected.values()))
        print(f'{"EXTRACTED" if args.write else "WOULD EXTRACT"} {source_relative}: {len(selected)}/{total} rows {counts}')
        if batch:
            with (batch / 'manifest.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(source=str(source), log=str(log), output=str(source_relative),
                                             source_rows=total, original_row_indices=list(selected),
                                             status_counts=counts)) + '\n')
        if args.limit and files >= args.limit:
            break
    print(f'Scanned {scanned}; selected files {files}; selected rows {rows}; corrupt logs {corrupt}; skipped {skipped}.')
    if batch:
        print(f'Retry data root: {batch}')
    if quarantine_batch:
        print(f'Corrupt-log quarantine: {quarantine_batch}')
    if not args.write:
        print('Preview only; use --write to extract rows and quarantine corrupt logs.')
    elif batch is None and quarantine_batch is None:
        print('No files written.')
    return 1 if skipped else 0


if __name__ == '__main__':
    sys.exit(main())
