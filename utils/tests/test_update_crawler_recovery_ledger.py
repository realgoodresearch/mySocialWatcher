import contextlib
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'recovery_ledger', Path(__file__).parents[1] / 'update_crawler_recovery_ledger.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_log(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', newline='') as stream:
        csv.writer(stream).writerows(rows)


class RecoveryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'retries'
        self.batch = self.root / '20261014T000000Z-test'
        self.batch.mkdir(parents=True)
        self.source = Path('host/collection/finished/dataframe_collected_finished_test.csv.gz')
        entry = {'output': self.source.as_posix(), 'original_row_indices': [4, 9, 15]}
        (self.batch / 'manifest.jsonl').write_text(json.dumps(entry) + '\n')
        log = (self.batch / 'crawler' / self.source).with_name(
            'dataframe_collected_finished_test_log.csv.gz'
        )
        write_log(log, [
            ['', 'timestamp_api', 'status_api'],
            ['0', 'one', '200'], ['1', 'two', '409'], ['2', 'three', '400'],
        ])

    def run_cli(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return module.main([str(self.root)])

    def test_records_only_successful_rows_and_is_idempotent(self):
        self.assertEqual(self.run_cli(), 0)
        ledger = self.root / 'recovery-ledger.jsonl'
        records = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([(r['row_index'], r['retry_status']) for r in records], [(4, 200), (9, 409)])
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(len(ledger.read_text().splitlines()), 2)

    def test_incomplete_batch_is_not_recorded(self):
        next((self.batch / 'crawler').rglob('*_log.csv.gz')).unlink()
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual((self.root / 'recovery-ledger.jsonl').read_text(), '')


if __name__ == '__main__':
    unittest.main()
