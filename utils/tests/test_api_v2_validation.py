import unittest
from datetime import date

from pydantic import ValidationError

from mysocialwatcher.api_v2.validation import normalize_row


def row(**changes):
    value = {
        "source_index": 7,
        "platform": "facebook",
        "timestamp": 1722470400,
        "geo_locations": {"name": "countries", "values": ["CI"]},
        "gender": 0,
        "age_min": 18,
        "age_max": 65,
        "dau": 100,
        "mau": 200,
        "valid": True,
        "all_fields": {"place": "Côte d'Ivoire"},
        "targeting": {"locales": ["العربية", "עברית"]},
        "response": {"data": [{"estimate_ready": True}]},
    }
    value.update(changes)
    return value


class ValidationTests(unittest.TestCase):
    def test_normalizes_valid_unicode_row_without_sql_quoting(self):
        result = normalize_row(row())
        self.assertEqual(result.table, "facebook")
        self.assertEqual(result.country, "CI")
        self.assertEqual(result.collection_date, date(2024, 8, 1))
        self.assertEqual(result.all_fields["place"], "Côte d'Ivoire")

    def test_geo_country_replaces_supplied_country(self):
        self.assertEqual(normalize_row(row(country="GB")).country, "CI")

    def test_not_ready_is_routed_to_invalid_table(self):
        response = {"data": [{"estimate_ready": False}]}
        self.assertEqual(normalize_row(row(response=response)).table, "facebook_invalid")

    def test_requires_an_audience_estimate(self):
        with self.assertRaises(ValidationError):
            normalize_row(row(mau=None, mau_lower=None, mau_upper=None))

    def test_rejects_ambiguous_country(self):
        geo = {"values": [{"country_code": "GB"}, {"country_code": "FR"}]}
        with self.assertRaisesRegex(ValueError, "more than one"):
            normalize_row(row(geo_locations=geo))

    def test_rejects_unverifiable_response(self):
        with self.assertRaisesRegex(ValueError, "estimate ready"):
            normalize_row(row(response={"data": []}))


if __name__ == "__main__":
    unittest.main()
