#!/usr/bin/env python3
"""Summarize crawler failures without changing source data or crawler logs."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from pathlib import Path
import re
import sys
import zlib

csv.field_size_limit(sys.maxsize)


def integer(value):
    try:
        number = Decimal(value.strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (AttributeError, InvalidOperation, ValueError):
        raise ValueError(f'invalid integer: {value!r}') from None


def utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except (AttributeError, ValueError):
        raise argparse.ArgumentTypeError(
            f'invalid date/time {value!r}; use YYYY-MM-DD or ISO 8601'
        ) from None


def category(status, message):
    text = message or ''
    lower = text.lower()
    if 'is not a valid json' in lower:
        return 'invalid JSON'
    if 'at least one of these arguments are required' in lower and 'mau' in lower:
        return 'missing MAU values'
    if 'all of these arguments are required' in lower:
        return 'missing required arguments'
    if 'no partition of relation' in lower:
        return 'missing database partition'
    if 'cannot assign requested address' in lower or 'database temporarily unavailable' in lower:
        return 'database connection unavailable'
    if 'internal server error' in lower and 'expecting value' in lower:
        return 'unclassified HTML API error'
    if status == 401:
        return 'authentication failure'
    collapsed = re.sub(r'\s+', ' ', text).strip()
    return collapsed[:240] or 'empty error message'


def scan_log(path):
    statuses = Counter()
    failures = Counter()
    samples = {}
    rows = 0
    with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames.count('status_api') != 1:
            raise ValueError('expected one status_api column')
        for row in reader:
            rows += 1
            status = integer(row.get('status_api'))
            if not 100 <= status <= 599:
                raise ValueError(f'invalid HTTP status {status}')
            statuses[status] += 1
            if not (200 <= status < 300 or status == 409):
                message = row.get('message_api', '')
                key = (status, category(status, message))
                failures[key] += 1
                samples.setdefault(key, re.sub(r'\s+', ' ', message).strip()[:500])
    if rows == 0:
        raise ValueError('empty response log')
    return statuses, failures, samples


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('crawler_dir', type=Path, help='crawler log root, e.g. data/crawler')
    parser.add_argument('--modified-after', type=utc_timestamp, metavar='DATETIME',
                        help='include logs modified at or after this UTC date/time')
    parser.add_argument('--modified-before', type=utc_timestamp, metavar='DATETIME',
                        help='include logs modified before this UTC date/time')
    parser.add_argument('--top', type=int, default=20,
                        help='number of failure categories to print (default: 20)')
    parser.add_argument('--output', type=Path,
                        help='write detailed grouped results to this CSV file')
    args = parser.parse_args(argv)
    root = args.crawler_dir.resolve()
    if not root.is_dir():
        parser.error(f'not a directory: {root}')
    if args.top < 1:
        parser.error('--top must be positive')
    if (args.modified_after is not None and args.modified_before is not None
            and args.modified_after >= args.modified_before):
        parser.error('--modified-after must be earlier than --modified-before')

    status_totals = Counter()
    category_totals = Counter()
    grouped = {}
    scanned = corrupt = 0
    for path in root.rglob('*_log.csv.gz'):
        try:
            modified = path.lstat().st_mtime
            if args.modified_after is not None and modified < args.modified_after:
                continue
            if args.modified_before is not None and modified >= args.modified_before:
                continue
            relative = path.relative_to(root)
            year = datetime.fromtimestamp(modified, timezone.utc).year
            collection = relative.parent.parent.as_posix()
            statuses, failures, samples = scan_log(path)
            scanned += 1
            status_totals.update(statuses)
            seen = set()
            for (status, label), rows in failures.items():
                category_totals[(status, label)] += rows
                key = (year, collection, status, label)
                record = grouped.setdefault(key, {
                    'rows': 0, 'files': 0, 'sample_message': samples[(status, label)]
                })
                record['rows'] += rows
                if key not in seen:
                    record['files'] += 1
                    seen.add(key)
        except (OSError, EOFError, gzip.BadGzipFile, zlib.error, UnicodeError,
                csv.Error, ValueError):
            corrupt += 1

    print(f'Scanned logs: {scanned}; corrupt/unreadable logs: {corrupt}')
    print('Rows by status: ' + (', '.join(
        f'{status}={rows}' for status, rows in sorted(status_totals.items())
    ) or 'none'))
    print('Failure categories:')
    if category_totals:
        for (status, label), rows in category_totals.most_common(args.top):
            print(f'  {status}  {rows:>12}  {label}')
    else:
        print('  none')

    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow([
                'modified_year', 'collection_path', 'status', 'category',
                'rows', 'files', 'sample_message'
            ])
            for key in sorted(grouped):
                record = grouped[key]
                writer.writerow([*key, record['rows'], record['files'], record['sample_message']])
        print(f'Detailed report: {output} ({len(grouped)} grouped records)')
    return 1 if corrupt else 0


if __name__ == '__main__':
    sys.exit(main())
