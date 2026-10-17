import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

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
            "timestamp_api": "now", "status_api": 200, "message_api": "OK"
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


if __name__ == "__main__":
    unittest.main()
