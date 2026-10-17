import unittest

from fastapi.testclient import TestClient

from mysocialwatcher.api_v2.database import AuthenticationError
from mysocialwatcher.api_v2.main import app, get_registry_writer, get_writer


def payload():
    return {
        "token": "test",
        "collection": "test",
        "rows": [{
            "source_index": 0,
            "platform": "facebook",
            "timestamp": 1722470400,
            "geo_locations": {"name": "countries", "values": ["GB"]},
            "gender": 0,
            "age_min": 18,
            "dau": 100,
            "mau": 200,
            "valid": True,
            "response": {"data": [{"estimate_ready": True}]},
        }],
    }


class Writer:
    def write(self, token, collection, rows):
        return {row.source_index for row in rows}


class RegistryWriter:
    def __init__(self):
        self.calls = []

    def start(self, mode, request):
        self.calls.append(("start", mode, request))
        return {"decision": "observe" if mode == "observe" else "process", "attempt_id": 7,
                "attempt_token": "e0f63a70-2216-45ce-9c23-0f425d5972e0",
                "lease_expires_at": None if mode == "observe" else "2026-01-01T00:00:00+00:00"}

    def renew(self, attempt_id, request):
        self.calls.append(("renew", attempt_id, request))
        return "2026-01-01T00:00:00+00:00"

    def finish(self, attempt_id, request):
        self.calls.append(("finish", attempt_id, request))


class RouteTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_does_not_need_database_configuration(self):
        response = TestClient(app).get("/socialwatcher/v2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_write_batch(self):
        app.dependency_overrides[get_writer] = lambda: Writer()
        response = TestClient(app).post("/socialwatcher/v2/write-batch", json=payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["inserted"], 1)

    def test_unauthorized_is_401(self):
        class Unauthorized:
            def write(self, token, collection, rows):
                raise AuthenticationError("token is not authorized for writes")

        app.dependency_overrides[get_writer] = lambda: Unauthorized()
        response = TestClient(app).post("/socialwatcher/v2/write-batch", json=payload())
        self.assertEqual(response.status_code, 401)

    def test_registry_routes_are_v2_and_do_not_expose_tokens(self):
        writer = RegistryWriter()
        app.dependency_overrides[get_registry_writer] = lambda: writer
        request_id = "123e4567-e89b-12d3-a456-426614174000"
        body = {
            "token": "registry-secret", "content_sha256": "a" * 64,
            "relative_path": "collector/file.csv.gz", "uncompressed_size": 123,
            "collection": "collector", "crawler_instance": "crawler-1", "request_id": request_id,
        }
        client = TestClient(app)
        observe = client.post("/socialwatcher/v2/files/observe", json=body)
        claim = client.post("/socialwatcher/v2/files/claim", json=body)
        self.assertEqual((observe.status_code, observe.json()["decision"]), (200, "observe"))
        self.assertEqual((claim.status_code, claim.json()["decision"]), (200, "process"))
        secret = observe.json()["attempt_token"]
        renew = client.post("/socialwatcher/v2/file-attempts/7/renew", json={
            "token": "registry-secret", "attempt_token": secret,
        })
        finish = client.post("/socialwatcher/v2/file-attempts/7/finish", json={
            "token": "registry-secret", "attempt_token": secret, "outcome": "completed",
            "total_rows": 1, "rows_200": 1,
        })
        self.assertEqual(renew.status_code, 200)
        self.assertEqual(finish.status_code, 204)
        self.assertEqual([call[0] for call in writer.calls], ["start", "start", "renew", "finish"])

    def test_validation_error_does_not_echo_token_or_request_values(self):
        secret = "never-echo-this-token"
        app.dependency_overrides[get_writer] = lambda: Writer()
        response = TestClient(app).post(
            "/socialwatcher/v2/write-batch",
            json={"token": secret, "collection": "test"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        self.assertNotIn("input", response.text)
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "rows"])


if __name__ == "__main__":
    unittest.main()
