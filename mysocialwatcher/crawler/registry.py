"""Best-effort API v2 file-registry observation helpers.

Observation is deliberately diagnostic: callers catch RegistryError and continue
the existing crawl, including its CSV-log skip and completion behavior.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from uuid import uuid4

import requests


class RegistryError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def relative_source_path(data_dir: Path, source: Path) -> str:
    try:
        return source.resolve().relative_to(data_dir.resolve()).as_posix()
    except ValueError as exc:
        raise RegistryError("source path is outside the configured data directory") from exc


class RegistryObserver:
    def __init__(self, url: str, token: str, crawler_instance: str,
                 session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.token = token
        self.crawler_instance = crawler_instance
        self.session = session or requests.Session()

    def observe(self, data_dir: Path, source: Path, collection: str) -> dict:
        content_hash, uncompressed_size = decompressed_sha256(source)
        payload = {
            "token": self.token,
            "content_sha256": content_hash,
            "relative_path": relative_source_path(data_dir, source),
            "uncompressed_size": uncompressed_size,
            "archive_sha256": sha256_file(source),
            "archive_size": source.stat().st_size,
            "collection": collection,
            "crawler_instance": self.crawler_instance,
            "request_id": str(uuid4()),
        }
        try:
            response = self.session.post(f"{self.url}/files/observe", json=payload, timeout=(10, 30))
            response.raise_for_status()
            body = response.json()
        except (ValueError, requests.RequestException) as exc:
            raise RegistryError(f"registry observation start failed: {type(exc).__name__}") from exc
        if body.get("decision") != "observe" or not body.get("attempt_id") or not body.get("attempt_token"):
            raise RegistryError("registry observation returned an invalid attempt handle")
        return body

    def finish(self, attempt: dict, outcome: str, total_rows: int | None,
               status_counts: dict[int, int], error_summary: str | None = None) -> None:
        payload = {
            "token": self.token,
            "attempt_token": attempt["attempt_token"],
            "outcome": outcome,
            "total_rows": total_rows,
            "rows_200": status_counts.get(200, 0),
            "rows_409": status_counts.get(409, 0),
            "rows_400": status_counts.get(400, 0),
            "rows_401": status_counts.get(401, 0),
            "rows_5xx": sum(count for status, count in status_counts.items() if 500 <= status <= 599),
            "rows_other": sum(count for status, count in status_counts.items()
                              if status not in {200, 400, 401, 409} and not 500 <= status <= 599),
            "corrupt_rows": 0,
            "error_summary": error_summary,
        }
        try:
            response = self.session.post(f"{self.url}/file-attempts/{attempt['attempt_id']}/finish",
                                         json=payload, timeout=(10, 30))
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RegistryError(f"registry observation completion failed: {type(exc).__name__}") from exc
