import unittest

from fastapi.testclient import TestClient

from mysocialwatcher.api_v2.database import AuthenticationError
from mysocialwatcher.api_v2.main import app, get_writer


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
