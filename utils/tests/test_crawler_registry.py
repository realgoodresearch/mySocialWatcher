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
        if url.endswith("/files/observe"):
            return Response({"decision": "observe", "attempt_id": 1, "attempt_token": "token"})
        return Response({})


class RegistryHashingTests(unittest.TestCase):
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
                        {200: 2, 409: 3, 400: 1, 503: 1}, "non-terminal row outcomes")
        _, payload, _ = session.calls[0]
        self.assertEqual((payload["rows_200"], payload["rows_409"], payload["rows_400"], payload["rows_5xx"]),
                         (2, 3, 1, 1))
        self.assertNotIn("rows", payload)
        self.assertNotIn("source", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
