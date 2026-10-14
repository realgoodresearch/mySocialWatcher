import contextlib
import csv
import gzip
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'failure_report', Path(__file__).parents[1] / 'report_crawler_failures.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FailureReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'crawler'
        self.log = self.root / 'host/collection/finished/dataframe_collected_finished_test_log.csv.gz'
        self.log.parent.mkdir(parents=True)
        with gzip.open(self.log, 'wt', newline='') as stream:
            csv.writer(stream).writerows([
                ['', 'status_api', 'message_api'],
                ['0', '200', 'OK'],
                ['1', '409', 'duplicate'],
                ['2', '400', "Bad Request: 'all_fields' is not a valid json."],
                ['3', '400', "Bad Request: At least one of these arguments are required ['mau']."],
                ['4', '503', 'Database temporarily unavailable.'],
            ])

    def run_cli(self, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            result = module.main([str(self.root), *args])
        return result, stdout.getvalue()

    def test_summary_and_csv_output(self):
        output = Path(self.temp.name) / 'report.csv'
        result, stdout = self.run_cli('--output', str(output))
        self.assertEqual(result, 0)
        self.assertIn('200=1', stdout)
        self.assertIn('invalid JSON', stdout)
        self.assertIn('missing MAU values', stdout)
        self.assertIn('database connection unavailable', stdout)
        with output.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(sum(int(row['rows']) for row in rows), 3)
        self.assertEqual({row['collection_path'] for row in rows}, {'host/collection'})

    def test_date_range_can_exclude_log(self):
        result, stdout = self.run_cli('--modified-before', '2000-01-01')
        self.assertEqual(result, 0)
        self.assertIn('Scanned logs: 0', stdout)


if __name__ == '__main__':
    unittest.main()
