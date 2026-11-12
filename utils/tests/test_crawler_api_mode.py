import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

from mysocialwatcher.crawler.utils import crawler


class CrawlerModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "host/collection/finished/dataframe_collected_finished_test.csv.gz"
        self.source.parent.mkdir(parents=True)
        pd.DataFrame([{"value": 1}]).to_csv(self.source, index=False)
        self.root = root

    @staticmethod
    def response(*args, **kwargs):
        return pd.DataFrame([{
            "timestamp_api": "now", "status_api": 200,
            "action_api": "inserted", "message_api": "OK"
        }])

    def test_registry_url_is_required(self):
        with self.assertRaisesRegex(ValueError, "REGISTRY_URL is required"):
            crawler(str(self.root), "token", "http://v2")

    def test_registry_filters_by_filename_date_and_writes_separate_log(self):
        selected = self.source.with_name(
            "dataframe_collected_finished_test_20240115.csv.gz")
        excluded = self.source.with_name(
            "dataframe_collected_finished_test_20240215.csv.gz")
        self.source.rename(selected)
        pd.DataFrame([{"value": 2}]).to_csv(excluded, index=False)

        class Registry:
            def claim(self, *args):
                return {"decision": "process", "attempt_id": 5, "attempt_token": "token"}

            def renew(self, *args):
                return None

            def finish(self, *args):
                return None

        with patch("mysocialwatcher.crawler.utils.RegistryObserver", return_value=Registry()), \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2", side_effect=self.response) as v2:
            crawler(str(self.root), "token", "http://v2", registry_url="http://registry",
                    crawl_date_from="2024-01-01",
                    crawl_date_to="2024-01-31", crawl_path_prefix="host/",
                    crawler_instance="test")
        self.assertEqual(v2.call_count, 1)
        log = (self.root / "crawler/registry/host/collection/finished/"
               "dataframe_collected_finished_test_20240115_log.csv.gz")
        self.assertTrue(log.exists())

    def test_enforce_uses_registry_claim_and_clears_stale_temp_marker(self):
        selected = self.source.with_name(
            "dataframe_collected_finished_test_20240115.csv.gz")
        self.source.rename(selected)
        marker = (self.root / "crawler/registry/host/collection/finished/"
                  "dataframe_collected_finished_test_20240115_temp.txt")
        marker.parent.mkdir(parents=True)
        marker.write_text("stale", encoding="utf-8")

        class Registry:
            def claim(self, *args):
                return {"decision": "process", "attempt_id": 5, "attempt_token": "token"}

            def renew(self, *args):
                return None

            def finish(self, *args):
                return None

        def respond_without_marker(*args, **kwargs):
            self.assertFalse(marker.exists())
            return self.response()

        with patch("mysocialwatcher.crawler.utils.RegistryObserver", return_value=Registry()), \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2",
                   side_effect=respond_without_marker) as v2:
            crawler(str(self.root), "token", "http://v2", registry_url="http://registry",
                    crawl_date_from="2024-01-01", crawl_date_to="2024-01-31")

        self.assertEqual(v2.call_count, 1)
        self.assertFalse(marker.exists())

    def test_enforce_request_failure_can_retry_without_temp_cleanup(self):
        selected = self.source.with_name(
            "dataframe_collected_finished_test_20240115.csv.gz")
        self.source.rename(selected)

        class Registry:
            def __init__(self):
                self.claims = 0
                self.finished = []

            def claim(self, *args):
                self.claims += 1
                decision = "process" if self.claims == 1 else "retry"
                return {"decision": decision, "attempt_id": self.claims,
                        "attempt_token": f"token-{self.claims}"}

            def renew(self, *args):
                return None

            def finish(self, *args):
                self.finished.append(args)

        registry = Registry()
        with patch("mysocialwatcher.crawler.utils.RegistryObserver", return_value=registry), \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2",
                   side_effect=[requests.RequestException("temporary failure"),
                                self.response()]) as v2:
            for _ in range(2):
                crawler(str(self.root), "token", "http://v2", registry_url="http://registry",
                        crawl_date_from="2024-01-01", crawl_date_to="2024-01-31")

        marker = (self.root / "crawler/registry/host/collection/finished/"
                  "dataframe_collected_finished_test_20240115_temp.txt")
        log = marker.with_name("dataframe_collected_finished_test_20240115_log.csv.gz")
        self.assertEqual(v2.call_count, 2)
        self.assertEqual(registry.claims, 2)
        self.assertFalse(marker.exists())
        self.assertTrue(log.exists())

    def test_enforce_uses_registry_despite_legacy_completion_log(self):
        legacy_log = (self.root / "crawler/host/collection/finished/"
                      "dataframe_collected_finished_test_log.csv.gz")
        legacy_log.parent.mkdir(parents=True)
        legacy_log.write_text("legacy", encoding="utf-8")

        class Registry:
            def claim(self, *args):
                return {"decision": "process", "attempt_id": 5,
                        "attempt_token": "token"}

            def renew(self, *args):
                return None

            def finish(self, *args):
                return None

        with patch("mysocialwatcher.crawler.utils.RegistryObserver",
                   return_value=Registry()), \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2",
                   side_effect=self.response) as v2:
            crawler(str(self.root), "token", "http://v2", registry_url="http://registry")

        self.assertEqual(v2.call_count, 1)
        self.assertEqual(legacy_log.read_text(encoding="utf-8"), "legacy")
        registry_log = (self.root / "crawler/registry/host/collection/finished/"
                        "dataframe_collected_finished_test_log.csv.gz")
        self.assertTrue(registry_log.exists())


if __name__ == "__main__":
    unittest.main()
