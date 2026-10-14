import os
import unittest

from sqlalchemy import create_engine, func, select

from mysocialwatcher.api_v2.database import (
    AUDIENCE_TABLES,
    AuthenticationError,
    BatchWriter,
    collections,
)
from mysocialwatcher.api_v2.validation import normalize_row


DATABASE_URL = os.environ.get("SOCIALWATCHER_V2_TEST_DATABASE_URL")


def row(source_index=0, **changes):
    value = {
        "source_index": source_index,
        "platform": "facebook",
        "timestamp": 1722470400,
        "geo_locations": {"name": "countries", "values": ["GB"]},
        "gender": 0,
        "age_min": 18,
        "dau": 100 + source_index,
        "mau": 200,
        "valid": True,
        "all_fields": {"place": "King's Cross"},
        "targeting": {"language": "العربية"},
        "response": {"data": [{"estimate_ready": True}]},
    }
    value.update(changes)
    return normalize_row(value)


@unittest.skipUnless(DATABASE_URL, "isolated test database URL not configured")
class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(DATABASE_URL)

    def setUp(self):
        with self.engine.begin() as connection:
            for table in AUDIENCE_TABLES.values():
                connection.execute(table.delete())
            connection.execute(collections.delete())
        self.writer = BatchWriter(self.engine)

    def test_bulk_insert_and_duplicate_accounting(self):
        rows = [row(0), row(1)]
        self.assertEqual(self.writer.write("v2-test-token", "_King's study_", rows), (2, 0))
        self.assertEqual(self.writer.write("v2-test-token", "_King's study_", rows), (0, 2))
        with self.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(AUDIENCE_TABLES["facebook"]))
            name = connection.scalar(select(collections.c.name))
        self.assertEqual(count, 2)
        self.assertEqual(name, "King's study")

    def test_unauthorized_batch_writes_nothing(self):
        with self.assertRaises(AuthenticationError):
            self.writer.write("wrong-token", "test", [row()])
        with self.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(AUDIENCE_TABLES["facebook"]))
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
