import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mysocialwatcher.crawler.registry import RegistryObserver, decompressed_sha256, relative_source_path


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError("HTTP failure")

    def json(self):
        return self.body


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        if url.endswith("/files/preflight"):
            return Response({"completed_paths": [item["relative_path"] for item in json["files"]]})
        if url.endswith("/files/observe"):
            return Response({"decision": "observe", "attempt_id": 1, "attempt_token": "token"})
        if url.endswith("/files/claim"):
            return Response({"decision": "process", "attempt_id": 2,
                             "attempt_token": "claim-token",
                             "lease_expires_at": "2026-11-10T00:15:00+00:00"})
        if url.endswith("/renew"):
            return Response({"lease_expires_at": "2026-11-10T00:20:00+00:00"})
        return Response({})


class RegistryHashingTests(unittest.TestCase):
    def test_preflight_uses_only_path_and_file_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "collector/finished/file.csv.gz"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not read by preflight")
            session = Session()
            registry = RegistryObserver("http://api/socialwatcher/v2", "secret", "crawler-1", session)

            result = registry.preflight(root, [source])

            self.assertEqual(result[source], (source.stat().st_size, source.stat().st_mtime_ns))
            url, payload, _ = session.calls[0]
            self.assertTrue(url.endswith("/files/preflight"))
            self.assertEqual(payload["files"][0]["relative_path"], "collector/finished/file.csv.gz")
            self.assertEqual(payload["files"][0]["archive_size"], source.stat().st_size)
            self.assertEqual(payload["files"][0]["archive_mtime_ns"], source.stat().st_mtime_ns)
            self.assertNotIn("content_sha256", payload)

    def test_hashes_decompressed_bytes_and_records_relative_archive_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "collector/finished/file.csv.gz"
            source.parent.mkdir(parents=True)
            raw = b"column,value\nexample,1\n"
            with gzip.GzipFile(source, "wb", mtime=0) as stream:
                stream.write(raw)
            digest, size = decompressed_sha256(source)
            self.assertEqual((digest, size), (hashlib.sha256(raw).hexdigest(), len(raw)))
            self.assertEqual(relative_source_path(root, source), "collector/finished/file.csv.gz")
            session = Session()
            observer = RegistryObserver("http://api/socialwatcher/v2", "secret", "crawler-1", session)
            attempt = observer.observe(root, source, "collector")
            self.assertEqual(attempt["attempt_id"], 1)
            _, payload, timeout = session.calls[0]
            self.assertEqual(payload["content_sha256"], digest)
            self.assertEqual(payload["archive_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(payload["relative_path"], "collector/finished/file.csv.gz")
            self.assertEqual(timeout, (10, 30))

    def test_finish_aggregates_statuses_without_sending_a_row_payload(self):
        session = Session()
        observer = RegistryObserver("http://api/socialwatcher/v2", "secret", "crawler-1", session)
        observer.finish({"attempt_id": 1, "attempt_token": "token"}, "failed", 7,
                        {200: 2, 409: 3, 400: 1, 503: 1},
                        {"inserted": 1, "promoted": 1, "unchanged": 3, "rejected": 1},
                        "non-terminal row outcomes")
        _, payload, _ = session.calls[0]
        self.assertEqual((payload["rows_200"], payload["rows_409"], payload["rows_400"], payload["rows_5xx"]),
                         (2, 3, 1, 1))
        self.assertEqual((payload["rows_inserted"], payload["rows_promoted"],
                          payload["rows_unchanged"], payload["rows_rejected"]),
                         (1, 1, 3, 1))
        self.assertNotIn("rows", payload)
        self.assertNotIn("source", json.dumps(payload))

    def test_enforced_claim_and_renew_use_the_attempt_handle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "collector/finished/file.csv.gz"
            source.parent.mkdir(parents=True)
            with gzip.open(source, "wb") as stream:
                stream.write(b"column,value\nexample,1\n")
            session = Session()
            registry = RegistryObserver("http://api/socialwatcher/v2", "secret", "crawler-1", session)
            attempt = registry.claim(root, source, "collector", lease_seconds=120)
            registry.renew(attempt, lease_seconds=120)
            self.assertEqual(attempt["decision"], "process")
            self.assertTrue(session.calls[0][0].endswith("/files/claim"))
            self.assertEqual(session.calls[0][1]["lease_seconds"], 120)
            self.assertTrue(session.calls[1][0].endswith("/file-attempts/2/renew"))
            self.assertEqual(session.calls[1][1]["attempt_token"], "claim-token")


if __name__ == "__main__":
    unittest.main()
