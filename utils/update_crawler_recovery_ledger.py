#!/usr/bin/env python3
"""Record successful retry rows so later extractions do not select them again."""

import argparse
import csv
from decimal import Decimal, InvalidOperation
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

csv.field_size_limit(sys.maxsize)


def integer(value):
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (InvalidOperation, ValueError):
        raise ValueError(f'invalid integer: {value!r}') from None


def safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or '..' in path.parts:
        raise ValueError(f'unsafe relative path: {value!r}')
    return Path(*path.parts)


def existing_records(path):
    records = {}
    if not path.exists():
        return records
    with path.open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                source = safe_relative(record['source']).as_posix()
                row_index = integer(record['row_index'])
                status = integer(record['retry_status'])
                if row_index < 0 or not (200 <= status < 300 or status == 409):
                    raise ValueError
            except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f'invalid ledger line {line_number}') from exc
            records[(source, row_index)] = record
    return records


def retry_results(path, expected_rows):
    results = []
    with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames.count('status_api') != 1:
            raise ValueError('retry log must contain one status_api column')
        for position, row in enumerate(reader):
            if '' not in row or integer(row['']) != position:
                raise ValueError('retry log indices must be ordered positions starting at zero')
            status = integer(row['status_api'])
            if not 100 <= status <= 599:
                raise ValueError(f'invalid retry status {status}')
            results.append((status, row.get('timestamp_api')))
    if len(results) != expected_rows:
        raise ValueError(f'retry log has {len(results)} rows; expected {expected_rows}')
    return results


def update(root, ledger):
    records = existing_records(ledger)
    batches = entries = recovered = incomplete = 0
    for manifest in sorted(root.glob('*/manifest.jsonl')):
        batch = manifest.parent
        batches += 1
        with manifest.open(encoding='utf-8') as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                entries += 1
                try:
                    entry = json.loads(line)
                    source = safe_relative(entry['output'])
                    indices = [integer(value) for value in entry['original_row_indices']]
                    if len(indices) != len(set(indices)) or any(value < 0 for value in indices):
                        raise ValueError('invalid original row indices')
                except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f'{manifest}: invalid line {line_number}: {exc}') from exc
                retry_log = (batch / 'crawler' / source).with_name(
                    source.name.removesuffix('.csv.gz') + '_log.csv.gz'
                )
                if not retry_log.is_file():
                    incomplete += 1
                    continue
                for original_index, (status, timestamp) in zip(
                    indices, retry_results(retry_log, len(indices))
                ):
                    if 200 <= status < 300 or status == 409:
                        key = (source.as_posix(), original_index)
                        records[key] = {
                            'source': key[0],
                            'row_index': original_index,
                            'retry_status': status,
                            'retry_timestamp': timestamp,
                            'retry_batch': batch.name,
                        }
                        recovered += 1

    ledger.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.recovery-ledger-', dir=ledger.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            for key in sorted(records):
                stream.write(json.dumps(records[key], sort_keys=True) + '\n')
        os.replace(temporary_name, ledger)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return batches, entries, recovered, incomplete, len(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('retry_root', type=Path, help='retry root containing timestamped batches')
    parser.add_argument('--ledger', type=Path, help='ledger path (default: RETRY_ROOT/recovery-ledger.jsonl)')
    args = parser.parse_args(argv)
    root = args.retry_root.resolve()
    ledger = (args.ledger or root / 'recovery-ledger.jsonl').resolve()
    if not root.is_dir():
        parser.error(f'not a directory: {root}')
    try:
        batches, entries, recovered, incomplete, total = update(root, ledger)
    except (OSError, EOFError, UnicodeError, csv.Error, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'Scanned {batches} batches and {entries} manifest entries; '
          f'observed {recovered} successful retries; incomplete entries {incomplete}.')
    print(f'Ledger: {ledger} ({total} recovered source rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
