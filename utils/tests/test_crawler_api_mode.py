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

    def test_v1_remains_default(self):
        with patch("mysocialwatcher.crawler.utils.psw_to_sql", side_effect=self.response) as v1, \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2") as v2:
            crawler(str(self.root), "token", "http://v1")
        v1.assert_called_once()
        v2.assert_not_called()

    def test_v2_must_be_selected_explicitly(self):
        with patch("mysocialwatcher.crawler.utils.psw_to_sql") as v1, \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2", side_effect=self.response) as v2:
            crawler(str(self.root), "token", "http://v2", api_mode="v2", batch_size=25)
        v1.assert_not_called()
        self.assertEqual(v2.call_args.kwargs["batch_size"], 25)

    def test_observe_mode_records_without_changing_v2_or_csv_skip(self):
        class Observer:
            def __init__(self, *args):
                self.finished = []

            def observe(self, data_dir, source, collection):
                return {"decision": "observe", "attempt_id": 4, "attempt_token": "token"}

            def finish(self, *args):
                self.finished.append(args)

        observer = Observer()
        def respond_while_marker_exists(*args, **kwargs):
            marker = (self.root / "crawler/host/collection/finished/"
                      "dataframe_collected_finished_test_temp.txt")
            self.assertTrue(marker.exists())
            return self.response()

        with patch("mysocialwatcher.crawler.utils.RegistryObserver", return_value=observer), \
             patch("mysocialwatcher.crawler.utils.submit_dataframe_v2",
                   side_effect=respond_while_marker_exists) as v2:
            crawler(str(self.root), "token", "http://v2", api_mode="v2", registry_mode="observe",
                    registry_url="http://registry/socialwatcher/v2", crawler_instance="test")
        self.assertEqual(v2.call_count, 1)
        self.assertEqual(len(observer.finished), 1)
        self.assertTrue((self.root / "crawler/host/collection/finished/dataframe_collected_finished_test_log.csv.gz").exists())

    def test_registry_requires_v2(self):
        with self.assertRaisesRegex(ValueError, "requires API_MODE=v2"):
            crawler(str(self.root), "token", "http://v1", registry_mode="observe", registry_url="http://registry")

    def test_historical_mode_filters_by_filename_date_and_writes_separate_log(self):
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
            crawler(str(self.root), "token", "http://v2", api_mode="v2",
                    registry_mode="enforce", registry_url="http://registry",
                    crawl_run_mode="historical", crawl_date_from="2024-01-01",
                    crawl_date_to="2024-01-31", crawl_path_prefix="host/",
                    recrawl_run_id="batch-001")
        self.assertEqual(v2.call_count, 1)
        log = (self.root / "crawler/recrawl/batch-001/host/collection/finished/"
               "dataframe_collected_finished_test_20240115_log.csv.gz")
        self.assertTrue(log.exists())

    def test_enforce_uses_registry_claim_and_clears_stale_temp_marker(self):
        selected = self.source.with_name(
            "dataframe_collected_finished_test_20240115.csv.gz")
        self.source.rename(selected)
        marker = (self.root / "crawler/recrawl/batch-001/host/collection/finished/"
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
            crawler(str(self.root), "token", "http://v2", api_mode="v2",
                    registry_mode="enforce", registry_url="http://registry",
                    crawl_run_mode="historical", crawl_date_from="2024-01-01",
                    crawl_date_to="2024-01-31", recrawl_run_id="batch-001")

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
                crawler(str(self.root), "token", "http://v2", api_mode="v2",
                        registry_mode="enforce", registry_url="http://registry",
                        crawl_run_mode="historical", crawl_date_from="2024-01-01",
                        crawl_date_to="2024-01-31", recrawl_run_id="batch-001")

        marker = (self.root / "crawler/recrawl/batch-001/host/collection/finished/"
                  "dataframe_collected_finished_test_20240115_temp.txt")
        log = marker.with_name("dataframe_collected_finished_test_20240115_log.csv.gz")
        self.assertEqual(v2.call_count, 2)
        self.assertEqual(registry.claims, 2)
        self.assertFalse(marker.exists())
        self.assertTrue(log.exists())

    def test_historical_mode_requires_enforcement_run_id_and_filter(self):
        with self.assertRaisesRegex(ValueError, "REGISTRY_MODE=enforce"):
            crawler(str(self.root), "token", "http://v2", api_mode="v2",
                    crawl_run_mode="historical", recrawl_run_id="batch",
                    crawl_date_from="2024-01-01")
        with self.assertRaisesRegex(ValueError, "date bound or path prefix"):
            crawler(str(self.root), "token", "http://v2", api_mode="v2",
                    registry_mode="enforce", registry_url="http://registry",
                    crawl_run_mode="historical", recrawl_run_id="batch")


if __name__ == "__main__":
    unittest.main()
