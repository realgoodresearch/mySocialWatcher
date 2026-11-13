"""Capped concurrent write-batch benchmark for the isolated API v2 Compose stack."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request


def row(batch: int, position: int) -> dict:
    identity = batch * 10_000 + position
    return {
        "source_index": position,
        "platform": "facebook",
        "timestamp": 1_700_000_000 + identity,
        "geo_locations": {"name": "countries", "values": ["GB"]},
        "gender": 0,
        "age_min": 18,
        "age_max": 65,
        "dau": -1,
        "mau_lower": 1_000 + (identity % 100),
        "mau_upper": 2_000 + (identity % 100),
        "valid": True,
        "all_fields": {"benchmark": True},
        "targeting": {"geo_locations": {"countries": ["GB"]}, "benchmark": identity},
        "response": {"data": [{"estimate_ready": True}]},
    }


def write_batch(url: str, token: str, batch: int, rows_per_batch: int) -> float:
    started = time.monotonic()
    body = json.dumps({
        "token": token,
        "collection": "api_v2_benchmark",
        "rows": [row(batch, position) for position in range(rows_per_batch)],
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    if result["accepted"] != rows_per_batch or result["rejected"] != 0:
        raise RuntimeError(f"unexpected batch result: {result}")
    return time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18001/socialwatcher/v2/write-batch")
    parser.add_argument("--token", default="v2-test-token")
    parser.add_argument("--batches", type=int, default=24)
    parser.add_argument("--rows-per-batch", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if min(args.batches, args.rows_per_batch, args.concurrency) < 1:
        raise ValueError("batches, rows per batch, and concurrency must be positive")

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        durations = list(executor.map(
            lambda batch: write_batch(args.url, args.token, batch, args.rows_per_batch),
            range(args.batches),
        ))
    elapsed = time.monotonic() - started
    print(json.dumps({
        "batches": args.batches,
        "rows": args.batches * args.rows_per_batch,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "rows_per_second": round(args.batches * args.rows_per_batch / elapsed, 1),
        "slowest_batch_seconds": round(max(durations), 3),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
