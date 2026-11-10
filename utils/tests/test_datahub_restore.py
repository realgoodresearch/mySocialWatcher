"""Safety tests for the guarded datahub restore script."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "utils" / "backup" / "datahub_restore.sh"


class DatahubRestoreScriptTests(unittest.TestCase):
    def make_backup(self, root: Path) -> Path:
        backup = root / "backup"
        backup.mkdir()
        for name, contents in (("database.dump", b"archive"), ("globals.sql", b"CREATE ROLE backup;\n")):
            (backup / name).write_bytes(contents)
        checksums = "".join(
            f"{hashlib.sha256((backup / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ("database.dump", "globals.sql")
        )
        (backup / "checksums.sha256").write_text(checksums)
        return backup

    def test_requires_explicit_target_and_confirmation(self):
        result = subprocess.run(["bash", str(SCRIPT)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--yes-really-restore", result.stderr)

    def test_verifies_then_restores_only_the_database_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup = self.make_backup(root)
            commands = root / "commands"
            commands.mkdir()
            calls = root / "docker-calls"
            docker = commands / "docker"
            docker.write_text(f'''#!/usr/bin/env bash
printf '%s\\n' "$*" >> {calls}
cat >/dev/null
''')
            docker.chmod(0o755)
            environment = os.environ | {"PATH": f"{commands}:{os.environ['PATH']}"}
            result = subprocess.run(
                ["bash", str(SCRIPT), "--backup-dir", str(backup), "--target-container", "restore-test",
                 "--yes-really-restore"],
                text=True, capture_output=True, env=environment, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = calls.read_text()
            self.assertIn("restore-test pg_restore", recorded)
            self.assertNotIn(" psql ", recorded)


@unittest.skipUnless(os.environ.get("RUN_DATAHUB_BACKUP_RESTORE_TEST") == "1",
                     "opt-in disposable PostgreSQL backup/restore integration test")
class DatahubBackupRestoreIntegrationTests(unittest.TestCase):
    """Exercises both scripts against isolated PostgreSQL 18 containers."""

    @classmethod
    def docker(cls, *args, check=True):
        return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)

    @classmethod
    def setUpClass(cls):
        suffix = uuid.uuid4().hex[:12]
        cls.source = f"socialwatcher-backup-source-{suffix}"
        cls.target = f"socialwatcher-backup-target-{suffix}"
        for name, database in ((cls.source, "social_media_audience"), (cls.target, "postgres")):
            cls.docker("run", "--detach", "--name", name, "--network", "none",
                       "-e", "POSTGRES_PASSWORD=disposable-test-only", "-e", f"POSTGRES_DB={database}",
                       "postgres:18")
            cls.addClassCleanup(lambda name=name: cls.docker("rm", "-f", name, check=False))
            ready = cls.docker("exec", name, "bash", "-c",
                               "for i in {1..30}; do pg_isready -U postgres >/dev/null && exit 0; sleep 1; done; exit 1",
                               check=False)
            if ready.returncode:
                raise RuntimeError(cls.docker("logs", name).stdout)
        cls.docker("exec", cls.source, "psql", "-U", "postgres", "-d", "social_media_audience",
                   "-c", "CREATE TABLE restore_fixture(id integer PRIMARY KEY, note text); "
                   "INSERT INTO restore_fixture VALUES (1, 'restored');")

    def test_backup_then_restore_preserves_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ | {"BACKUP_ROOT": temporary, "DATABASE_CONTAINER": self.source}
            backup = subprocess.run(["bash", str(ROOT / "utils" / "backup" / "datahub_backup.sh")],
                                    text=True, capture_output=True, env=environment, check=False)
            self.assertEqual(backup.returncode, 0, backup.stdout + backup.stderr)
            directories = list(Path(temporary).glob("datahub-db-*"))
            self.assertEqual(len(directories), 1)
            restore = subprocess.run(
                ["bash", str(SCRIPT), "--backup-dir", str(directories[0]), "--target-container", self.target,
                 "--yes-really-restore"], text=True, capture_output=True, env=os.environ, check=False,
            )
            self.assertEqual(restore.returncode, 0, restore.stdout + restore.stderr)
            restored = self.docker("exec", self.target, "psql", "-U", "postgres", "-d", "social_media_audience",
                                   "-Atc", "SELECT note FROM restore_fixture WHERE id = 1;")
            self.assertEqual(restored.stdout.strip(), "restored")


if __name__ == "__main__":
    unittest.main()
