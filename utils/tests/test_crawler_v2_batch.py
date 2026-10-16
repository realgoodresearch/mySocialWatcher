import json
import unittest

import pandas as pd

from mysocialwatcher.crawler.batch import dataframe_to_v2_rows, submit_dataframe_v2


def frame():
    return pd.DataFrame([{
        "publisher_platforms": "['facebook']",
        "all_fields": repr([("geo_locations", {"name": "countries", "values": ["CI"]}),
                            ("place", "Côte d'Ivoire")]),
        "targeting": repr({"locales": ["العربية", "עברית"]}),
        "response": json.dumps({"data": [{"estimate_ready": True}]}),
        "ages_ranges": repr({"min": 18, "max": 65}),
        "timestamp": 1722470400,
        "genders": 0,
        "dau_audience": 100,
        "mau_audience": 200,
    }])


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [{"source_index": 0, "status": 200, "message": "OK: row inserted."}],
            "errors": [],
        }


class FakeSession:
    def __init__(self):
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return FakeResponse()


class BatchClientTests(unittest.TestCase):
    def test_converts_legacy_fields_to_json_objects(self):
        rows, errors = dataframe_to_v2_rows(frame())
        self.assertFalse(errors)
        self.assertEqual(rows[0]["geo_locations"]["values"], ["CI"])
        self.assertEqual(rows[0]["all_fields"]["place"], "Côte d'Ivoire")
        self.assertEqual(rows[0]["targeting"]["locales"], ["العربية", "עברית"])

    def test_successful_batch_creates_compatible_log_columns(self):
        session = FakeSession()
        result = submit_dataframe_v2(frame(), "test", "token", "http://v2", session=session)
        self.assertEqual(result.loc[0, "status_api"], 200)
        self.assertEqual(list(result.columns), ["timestamp_api", "status_api", "message_api"])
        self.assertEqual(session.requests[0][1]["json"]["rows"][0]["source_index"], 0)

    def test_duplicate_result_is_written_as_409(self):
        class DuplicateResponse(FakeResponse):
            def json(self):
                return {
                    "results": [{"source_index": 0, "status": 409,
                                 "message": "Conflict: row already exists."}],
                    "errors": [],
                }

        class DuplicateSession(FakeSession):
            def post(self, url, **kwargs):
                self.requests.append((url, kwargs))
                return DuplicateResponse()

        result = submit_dataframe_v2(frame(), "test", "token", "http://v2",
                                     session=DuplicateSession())
        self.assertEqual(result.loc[0, "status_api"], 409)
        self.assertEqual(result.loc[0, "message_api"], "Conflict: row already exists.")


if __name__ == "__main__":
    unittest.main()
