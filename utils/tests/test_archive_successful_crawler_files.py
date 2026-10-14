import contextlib
import csv
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'archive_success', Path(__file__).parents[1] / 'archive_successful_crawler_files.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_gzip_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', newline='') as stream:
        csv.writer(stream).writerows(rows)


class ArchiveSuccessfulTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'hot/data'
        self.cold = self.root / 'cold'
        self.relative = Path('host/collection/finished/dataframe_collected_finished_test.csv.gz')
        self.source = self.data / self.relative
        self.log_relative = self.relative.with_name('dataframe_collected_finished_test_log.csv.gz')
        self.log = self.data / 'crawler' / self.log_relative
        write_gzip_csv(self.source, [['', 'value'], ['0', 'a'], ['1', 'b'], ['2', 'c']])

    def write_log(self, rows):
        write_gzip_csv(self.log, [['', 'status_api', 'message_api'], *rows])

    def run_cli(self, *args):
        if '--move' in args:
            self.cold.mkdir(parents=True, exist_ok=True)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = module.main([str(self.data), str(self.cold), *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_preview_then_verified_move(self):
        self.write_log([
            ['0', '200', 'OK'],
            ['1', '409', 'Conflict'],
            ['2', '400', "At least one of these arguments are required ['mau', 'mau_lower', 'mau_upper']."],
        ])
        before = self.source.read_bytes(), self.log.read_bytes()
        result, stdout, _ = self.run_cli()
        self.assertEqual(result, 0)
        self.assertIn('WOULD ARCHIVE', stdout)
        self.assertEqual((self.source.read_bytes(), self.log.read_bytes()), before)
        result, stdout, _ = self.run_cli('--move')
        self.assertEqual(result, 0)
        self.assertFalse(self.source.exists())
        self.assertFalse(self.log.exists())
        self.assertEqual((self.cold / 'data' / self.relative).read_bytes(), before[0])
        self.assertEqual((self.cold / 'data/crawler' / self.log_relative).read_bytes(), before[1])
        record = json.loads((self.cold / 'transfer-manifest.jsonl').read_text())
        self.assertEqual(record['rows'], 3)

    def test_unacceptable_400_is_not_archived(self):
        self.write_log([
            ['0', '200', 'OK'], ['1', '409', 'Conflict'],
            ['2', '400', "Bad Request: 'all_fields' is not a valid json."],
        ])
        result, stdout, _ = self.run_cli('--move')
        self.assertEqual(result, 0)
        self.assertNotIn('ARCHIVE', stdout)
        self.assertTrue(self.source.exists())
        self.assertTrue(self.log.exists())

    def test_ledger_recovery_makes_failed_row_acceptable(self):
        self.write_log([
            ['0', '200', 'OK'], ['1', '409', 'Conflict'],
            ['2', '400', "Bad Request: 'all_fields' is not a valid json."],
        ])
        ledger = self.root / 'ledger.jsonl'
        ledger.write_text(json.dumps({
            'source': self.relative.as_posix(), 'row_index': 2,
            'retry_status': 200,
        }) + '\n')
        result, stdout, _ = self.run_cli('--move', '--ledger', str(ledger))
        self.assertEqual(result, 0)
        self.assertIn('ledger-recovered:1', stdout)
        self.assertFalse(self.source.exists())

    def test_source_log_row_mismatch_is_blocked(self):
        self.write_log([['0', '200', 'OK'], ['1', '409', 'Conflict']])
        result, _, stderr = self.run_cli('--move')
        self.assertEqual(result, 1)
        self.assertIn('row count mismatch', stderr)
        self.assertTrue(self.source.exists())
        self.assertTrue(self.log.exists())

    def test_date_and_age_filters(self):
        self.write_log([['0', '200', 'OK'], ['1', '200', 'OK'], ['2', '200', 'OK']])
        modified = 946771200
        os.utime(self.log, (modified, modified))
        result, stdout, _ = self.run_cli(
            '--modified-after', '2000-01-01', '--modified-before', '2000-01-03'
        )
        self.assertEqual(result, 0)
        self.assertIn('WOULD ARCHIVE', stdout)
        result, stdout, _ = self.run_cli('--modified-after', '2000-01-03')
        self.assertEqual(result, 0)
        self.assertNotIn('WOULD ARCHIVE', stdout)


if __name__ == '__main__':
    unittest.main()
