#!/usr/bin/env python3
"""Parse a crawler CSV and optionally send it to an isolated API v2 instance."""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mysocialwatcher.crawler.batch import dataframe_to_v2_rows, submit_dataframe_v2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8001/socialwatcher/v2/write-batch")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--output", type=Path, help="required with --send; must not already exist")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()

    frame = pd.read_csv(args.source)
    rows, errors = dataframe_to_v2_rows(frame)
    print(f"Parsed {len(rows)}/{len(frame)} rows; client errors {len(errors)}.")
    if not args.send:
        return
    if args.output is None:
        parser.error("--output is required with --send")
    if args.output.exists():
        parser.error("--output must not already exist")
    token = os.environ.get("API_TOKEN")
    if not token:
        parser.error("API_TOKEN environment variable is required with --send")
    result = submit_dataframe_v2(frame, args.collection, token, args.url, args.batch_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=True)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
