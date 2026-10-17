"""Safety tests for the Borg-oriented logical datahub backup script."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "utils" / "datahub_backup.sh"


class DatahubBackupScriptTests(unittest.TestCase):
    def prepare(self, fail_restore: bool = False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        commands = root / "commands"
        commands.mkdir()
        docker = commands / "docker"
        restore = "cat >/dev/null; exit 1" if fail_restore else "cat >/dev/null; printf '1; 0 0 TABLE public example postgres\\n'"
        docker.write_text(f'''#!/usr/bin/env bash
set -Eeuo pipefail
case "${{4:-}}" in
  pg_dump) printf 'custom archive bytes' ;;
  pg_dumpall) printf 'CREATE ROLE backup_role;\\n' ;;
  pg_restore) {restore} ;;
  postgres) printf 'postgres (PostgreSQL) 18.6\\n' ;;
  *) printf 'unexpected docker invocation: %s\\n' "$*" >&2; exit 2 ;;
esac
''')
        docker.chmod(0o755)
        backup_root = root / "backups"
        environment = os.environ | {
            "PATH": f"{commands}:{os.environ['PATH']}",
            "BACKUP_ROOT": str(backup_root),
            "DATABASE_CONTAINER": "test-db",
        }
        return backup_root, environment

    def run_backup(self, backup_root: Path, environment: dict[str, str]):
        return subprocess.run(["bash", str(SCRIPT)], text=True, capture_output=True,
                              env=environment, check=False)

    def test_publishes_verified_backup_then_prunes_prior_routine_backup(self):
        backup_root, environment = self.prepare()
        previous = backup_root / "routine-2000-01-01T000000Z"
        previous.mkdir(parents=True)
        (previous / "database.dump").write_text("old backup")
        result = self.run_backup(backup_root, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(previous.exists())
        backups = list(backup_root.glob("routine-*"))
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        for name in ("database.dump", "globals.sql", "archive-contents.txt", "metadata.txt", "checksums.sha256"):
            self.assertTrue((backup / name).is_file())
        self.assertIn("Backup completed successfully", result.stdout)

    def test_failed_verification_preserves_existing_routine_backup(self):
        backup_root, environment = self.prepare(fail_restore=True)
        previous = backup_root / "routine-2000-01-01T000000Z"
        previous.mkdir(parents=True)
        result = self.run_backup(backup_root, environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(previous.is_dir())
        self.assertEqual(list(backup_root.glob(".*.staging.*")), [])


if __name__ == "__main__":
    unittest.main()
