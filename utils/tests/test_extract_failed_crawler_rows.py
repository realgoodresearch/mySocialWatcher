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

spec = importlib.util.spec_from_file_location('extract_rows', Path(__file__).parents[1] / 'extract_failed_crawler_rows.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', newline='') as stream:
        csv.writer(stream).writerows(rows)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.data = self.repo / 'data'
        self.relative = Path('host/collection/finished/dataframe_collected_finished_test.csv.gz')
        self.source = self.data / self.relative
        self.log = self.data / 'crawler' / self.relative.with_name('dataframe_collected_finished_test_log.csv.gz')
        # Saved source indices deliberately differ from parsed row positions.
        self.source_rows = [['', 'targeting'], ['99', 'a'], ['42', "name's, embedded\nnewline"], ['7', 'c'], ['3', 'd']]
        write_csv(self.source, self.source_rows)
        write_csv(self.log, [['', 'status_api'], ['0', '200'], ['1', '500.0'], ['2', '409'], ['3', '400']])

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return module.main([str(self.data), *args])

    def test_preview_and_selective_write(self):
        before = self.source.read_bytes(), self.log.read_bytes()
        self.assertEqual(self.run_cli(), 0)
        self.assertFalse((self.repo / 'crawler-retry-data').exists())
        self.assertEqual(self.run_cli('--write', '--status', '500'), 0)
        batch = next((self.repo / 'crawler-retry-data').iterdir())
        with gzip.open(batch / self.relative, 'rt', newline='') as stream:
            self.assertEqual(list(csv.reader(stream)), [self.source_rows[0], self.source_rows[2]])
        manifest = json.loads((batch / 'manifest.jsonl').read_text())
        self.assertEqual(manifest['original_row_indices'], [1])
        self.assertEqual((self.source.read_bytes(), self.log.read_bytes()), before)

    def test_ignore_status_excludes_rows(self):
        self.assertEqual(self.run_cli('--write', '--ignore-status', '400', '401'), 0)
        batch = next((self.repo / 'crawler-retry-data').iterdir())
        with gzip.open(batch / self.relative, 'rt', newline='') as stream:
            self.assertEqual(list(csv.reader(stream)), [self.source_rows[0], self.source_rows[2]])

    def test_ignore_overrides_status_and_can_select_nothing(self):
        self.assertEqual(self.run_cli('--write', '--status', '400', '500', '--ignore-status', '400', '500'), 0)
        self.assertFalse((self.repo / 'crawler-retry-data').exists())

    def test_invalid_ignored_status(self):
        for status in ('99', '600', 'abc'):
            with self.assertRaises(SystemExit):
                self.run_cli('--ignore-status', status)

    def test_corrupt_logs_quarantined_for_full_retry(self):
        for payload in (b'not gzip', gzip.compress(b',status_api\n0,500\n2,400\n')):
            self.log.write_bytes(payload)
            self.assertEqual(self.run_cli('--limit', '1', '--status', '502'), 0)
            self.assertTrue(self.log.exists())
            self.assertEqual(self.run_cli('--write', '--limit', '1', '--status', '502'), 0)
            self.assertFalse(self.log.exists())
            self.assertFalse(list((self.repo / 'crawler-retry-data').rglob('*.csv.gz')))
            archived = list((self.repo / 'crawler-log-quarantine').rglob('*_log.csv.gz'))
            self.assertIn(payload, [p.read_bytes() for p in archived])
            self.assertTrue(self.source.exists())

    def test_source_mismatch_does_not_quarantine_log(self):
        self.log.write_bytes(gzip.compress(b',status_api\n0,500\n'))
        self.assertEqual(self.run_cli('--write'), 1)
        self.assertTrue(self.log.exists())
        self.assertFalse(list((self.repo / 'crawler-retry-data').rglob('*.csv.gz')))
        self.assertFalse((self.repo / 'crawler-log-quarantine').exists())

    def test_markers_block_extraction(self):
        self.log.with_name('dataframe_collected_finished_test_temp.txt').touch()
        self.assertEqual(self.run_cli('--write'), 1)
        self.assertFalse((self.repo / 'crawler-retry-data').exists())

    def test_quarantined_logs_and_limit(self):
        archive = self.repo / 'quarantine/batch'
        relative_log = self.log.relative_to(self.data / 'crawler')
        dest = archive / relative_log
        dest.parent.mkdir(parents=True)
        self.log.rename(dest)
        older_source = self.source.with_name('dataframe_collected_finished_older.csv.gz')
        write_csv(older_source, self.source_rows)
        older_log = dest.with_name('dataframe_collected_finished_older_log.csv.gz')
        older_log.write_bytes(dest.read_bytes())
        os.utime(older_log, (1, 1))
        self.assertEqual(self.run_cli('--logs-dir', str(archive), '--limit', '1', '--write'), 0)
        batch = next((self.repo / 'crawler-retry-data').iterdir())
        self.assertTrue((batch / self.relative).exists())
        self.assertEqual(len(list(batch.rglob('*.csv.gz'))), 1)

    def test_unsafe_destination(self):
        with self.assertRaises(SystemExit):
            self.run_cli('--output-dir', str(self.data / 'retries'))


if __name__ == '__main__':
    unittest.main()
