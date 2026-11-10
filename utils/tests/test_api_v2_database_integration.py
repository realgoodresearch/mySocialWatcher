import os
import json
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select

from mysocialwatcher.api_v2.database import (
    AUDIENCE_TABLES,
    AuthenticationError,
    BatchWriter,
    collections,
)
from mysocialwatcher.api_v2.validation import normalize_row


DATABASE_URL = os.environ.get("SOCIALWATCHER_V2_TEST_DATABASE_URL")
REAL_FIXTURE = os.environ.get("SOCIALWATCHER_V2_REAL_FIXTURE")


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
        self.assertEqual(self.writer.write("v2-test-token", "_King's study_", rows),
                         {0: "inserted", 1: "inserted"})
        self.assertEqual(self.writer.write("v2-test-token", "_King's study_", rows), {})
        with self.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(AUDIENCE_TABLES["facebook"]))
            name = connection.scalar(select(collections.c.name))
        self.assertEqual(count, 2)
        self.assertEqual(name, "King's study")

    def test_duplicate_rows_within_one_batch_identify_only_one_insert(self):
        rows = [row(10), row(11, dau=110)]
        self.assertEqual(self.writer.write("v2-test-token", "test", rows), {10: "inserted"})

    def test_refinement_replaces_original_measurements(self):
        original = row(0, dau=100, mau=200, mau_lower=180, mau_upper=220,
                       all_fields={"query": "original"})
        refined = row(1, dau=100, mau=210, mau_lower=-1, mau_upper=230,
                      all_fields={"query": "refined", "better_estimates": True})

        self.assertEqual(self.writer.write("v2-test-token", "test", [original]),
                         {0: "inserted"})
        self.assertEqual(self.writer.write("v2-test-token", "test", [refined]),
                         {1: "promoted"})

        with self.engine.connect() as connection:
            stored = connection.execute(select(AUDIENCE_TABLES["facebook"])).mappings().one()
        self.assertEqual((stored["mau"], stored["mau_lower"], stored["mau_upper"]),
                         (210, -1, 230))
        self.assertTrue(stored["all_fields"]["better_estimates"])

    def test_original_does_not_replace_refinement(self):
        refined = row(0, dau=100, mau=210, mau_lower=-1, mau_upper=230,
                      all_fields={"better_estimates": True})
        original = row(1, dau=100, mau=200, mau_lower=180, mau_upper=220,
                       all_fields={"query": "original"})

        self.assertEqual(self.writer.write("v2-test-token", "test", [refined]),
                         {0: "inserted"})
        self.assertEqual(self.writer.write("v2-test-token", "test", [original]), {})

        with self.engine.connect() as connection:
            stored = connection.execute(select(AUDIENCE_TABLES["facebook"])).mappings().one()
        self.assertEqual(stored["mau"], 210)
        self.assertTrue(stored["all_fields"]["better_estimates"])

    def test_same_provenance_keeps_existing_row(self):
        original = row(0, dau=100, mau=200, all_fields={"query": "first"})
        later_original = row(1, dau=100, mau=300, all_fields={"query": "second"})
        refined = row(2, dau=101, mau=400, all_fields={"better_estimates": True})
        later_refined = row(3, dau=101, mau=500, all_fields={"better_estimates": True})

        self.assertEqual(self.writer.write("v2-test-token", "test", [original]),
                         {0: "inserted"})
        self.assertEqual(self.writer.write("v2-test-token", "test", [later_original]), {})
        self.assertEqual(self.writer.write("v2-test-token", "test", [refined]),
                         {2: "inserted"})
        self.assertEqual(self.writer.write("v2-test-token", "test", [later_refined]), {})

        with self.engine.connect() as connection:
            stored = connection.execute(
                select(AUDIENCE_TABLES["facebook"].c.dau, AUDIENCE_TABLES["facebook"].c.mau)
                .order_by(AUDIENCE_TABLES["facebook"].c.dau)
            ).all()
        self.assertEqual(stored, [(100, 200), (101, 400)])

    def test_batch_duplicate_prefers_refinement(self):
        original = row(10, dau=100, mau=200, all_fields={"query": "original"})
        refined = row(11, dau=100, mau=210,
                      all_fields={"better_estimates": True})

        self.assertEqual(self.writer.write("v2-test-token", "test", [original, refined]),
                         {11: "inserted"})
        with self.engine.connect() as connection:
            stored = connection.execute(select(AUDIENCE_TABLES["facebook"])).mappings().one()
        self.assertEqual(stored["mau"], 210)
        self.assertTrue(stored["all_fields"]["better_estimates"])

    @unittest.skipUnless(REAL_FIXTURE, "controlled production fixture not configured")
    def test_real_original_is_promoted_by_its_refinement(self):
        fixture = json.loads(Path(REAL_FIXTURE).read_text(encoding="utf-8"))
        stored = fixture["stored"]
        with self.engine.begin() as connection:
            collection_id = connection.execute(
                insert(collections).values(name=stored["collection"]).returning(collections.c.id)
            ).scalar_one()
            values = {
                key: value for key, value in stored.items()
                if key in AUDIENCE_TABLES[stored["platform"]].c
            }
            values.update(collection_id=collection_id, contributor_id=1)
            connection.execute(insert(AUDIENCE_TABLES[stored["platform"]]).values(values))

        refinement = normalize_row(fixture["incoming_refinement"])
        self.assertEqual(
            self.writer.write("v2-test-token", stored["collection"], [refinement]),
            {refinement.source_index: "promoted"},
        )

        with self.engine.connect() as connection:
            promoted = connection.execute(
                select(AUDIENCE_TABLES[stored["platform"]])
            ).mappings().one()
        self.assertEqual(
            (promoted["mau"], promoted["mau_lower"], promoted["mau_upper"]),
            (refinement.mau, refinement.mau_lower, refinement.mau_upper),
        )
        self.assertTrue(promoted["all_fields"]["better_estimates"])

    def test_unauthorized_batch_writes_nothing(self):
        with self.assertRaises(AuthenticationError):
            self.writer.write("wrong-token", "test", [row()])
        with self.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(AUDIENCE_TABLES["facebook"]))
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
