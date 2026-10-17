"""Safety tests for the guarded datahub restore script."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "utils" / "datahub_restore.sh"


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


if __name__ == "__main__":
    unittest.main()
