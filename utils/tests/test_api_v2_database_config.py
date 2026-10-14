import unittest
from unittest.mock import patch

from sqlalchemy.engine import URL

from mysocialwatcher.api_v2.database import engine_from_environment


class DatabaseConfigTests(unittest.TestCase):
    def test_builds_encoded_url_from_existing_postgres_environment(self):
        environment = {
            "POSTGRES_WPASS": "quote' slash/ at@ colon:",
            "POSTGRES_HOST": "datahub_db",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "social_media_audience",
        }
        with patch.dict("os.environ", environment, clear=True), \
             patch("mysocialwatcher.api_v2.database.create_engine") as create:
            engine_from_environment()
        url = create.call_args.args[0]
        self.assertIsInstance(url, URL)
        self.assertEqual(url.password, environment["POSTGRES_WPASS"])
        self.assertEqual(url.host, "datahub_db")

    def test_refuses_to_guess_missing_database_settings(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "missing"):
                engine_from_environment()


if __name__ == "__main__":
    unittest.main()
