#!/usr/bin/env python3
"""Benchmark an isolated API v2 instance with synthetic rows."""

import argparse
import concurrent.futures
import time

import requests


def make_rows(start, count):
    return [{
        "source_index": index,
        "platform": "facebook",
        "timestamp": 1722470400,
        "geo_locations": {"name": "countries", "values": ["GB"]},
        "gender": index % 3,
        "age_min": 18,
        "age_max": 65,
        "dau": 1_000_000 + start + index,
        "mau": 2_000_000 + start + index,
        "valid": True,
        "all_fields": {"benchmark": start + index},
        "targeting": {},
        "response": {"data": [{"estimate_ready": True}], "benchmark": start + index},
    } for index in range(count)]


def submit(url, token, collection, start, count):
    response = requests.post(
        url,
        json={"token": token, "collection": collection, "rows": make_rows(start, count)},
        timeout=(10, 300),
    )
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", default="v2-test-token")
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--clients", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")

    jobs = []
    base = args.run_id * 10_000_000
    for offset in range(0, args.rows, args.batch_size):
        jobs.append((base + offset, min(args.batch_size, args.rows - offset)))

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.clients) as executor:
        futures = [executor.submit(
            submit, args.url, args.token, f"benchmark_{args.run_id}", start, count
        ) for start, count in jobs]
        results = [future.result() for future in futures]
    elapsed = time.perf_counter() - started
    inserted = sum(result["inserted"] for result in results)
    rejected = sum(result["rejected"] for result in results)
    print(f"clients={args.clients} rows={args.rows} batch_size={args.batch_size} "
          f"inserted={inserted} rejected={rejected} seconds={elapsed:.3f} "
          f"rows_per_second={args.rows / elapsed:.1f}")


if __name__ == "__main__":
    main()
