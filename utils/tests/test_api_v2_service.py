import unittest

from mysocialwatcher.api_v2.database import AuthenticationError
from mysocialwatcher.api_v2.schemas import BatchWriteRequest
from mysocialwatcher.api_v2.service import process_batch


def valid_row(source_index=0, **changes):
    value = {
        "source_index": source_index,
        "platform": "facebook",
        "timestamp": 1722470400,
        "geo_locations": {"name": "countries", "values": ["GB"]},
        "gender": 0,
        "age_min": 18,
        "dau": 100,
        "mau": 200,
        "valid": True,
        "response": {"data": [{"estimate_ready": True}]},
    }
    value.update(changes)
    return value


class FakeWriter:
    def __init__(self, inserted=None):
        self.inserted = inserted
        self.call = None

    def write(self, token, collection, rows):
        self.call = (token, collection, rows)
        inserted = len(rows) if self.inserted is None else self.inserted
        return inserted, len(rows) - inserted


class BatchServiceTests(unittest.TestCase):
    def test_bad_row_does_not_reject_good_row(self):
        writer = FakeWriter()
        request = BatchWriteRequest(token="secret", collection="test", rows=[
            valid_row(0), valid_row(1, gender=9),
        ])
        result = process_batch(request, writer)
        self.assertEqual((result.received, result.accepted, result.rejected), (2, 1, 1))
        self.assertEqual(result.errors[0].source_index, 1)
        self.assertEqual(len(writer.call[2]), 1)

    def test_reports_inserted_and_duplicate_aggregates(self):
        writer = FakeWriter(inserted=1)
        result = process_batch(BatchWriteRequest(
            token="secret", collection="test", rows=[valid_row(0), valid_row(1)]
        ), writer)
        self.assertEqual((result.inserted, result.duplicates), (1, 1))

    def test_duplicate_source_index_is_rejected(self):
        writer = FakeWriter()
        result = process_batch(BatchWriteRequest(
            token="secret", collection="test", rows=[valid_row(2), valid_row(2)]
        ), writer)
        self.assertEqual((result.accepted, result.rejected), (1, 1))

    def test_authentication_error_is_not_converted_to_row_error(self):
        class UnauthorizedWriter(FakeWriter):
            def write(self, token, collection, rows):
                raise AuthenticationError("unauthorized")

        with self.assertRaises(AuthenticationError):
            process_batch(BatchWriteRequest(
                token="bad", collection="test", rows=[valid_row()]
            ), UnauthorizedWriter())


if __name__ == "__main__":
    unittest.main()
