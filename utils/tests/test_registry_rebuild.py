"""Opt-in full rebuild. Creates/removes only its own unique disposable container.

RUN_REGISTRY_REBUILD_TEST=1 python3 -m unittest utils.tests.test_registry_rebuild -v
No production URLs, credentials, networks, volumes, or host ports are used.
"""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('RUN_REGISTRY_REBUILD_TEST') == '1', 'opt-in disposable PostgreSQL test')
class RegistryRebuildTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args, input=None, check=True):
        return subprocess.run(['docker', *args], input=input, text=True,
                              capture_output=True, check=check)

    @classmethod
    def setUpClass(cls):
        cls.name = 'socialwatcher-registry-test-' + uuid.uuid4().hex[:12]
        cls.docker('run', '--detach', '--name', cls.name, '--network', 'none',
                   '--tmpfs', '/var/lib/postgresql',
                   '-e', 'POSTGRES_USER=registry_test', '-e', 'POSTGRES_DB=registry_test',
                   '-e', 'POSTGRES_PASSWORD=disposable-test-only',
                   '-e', 'POSTGRES_WPASS=writer-test', '-e', 'POSTGRES_RPASS=reader-test',
                   '-v', f'{ROOT}/docker/datahub/migrations:/schema/migrations:ro',
                   '-v', f'{ROOT}/docker/datahub/migrate.sh:/schema/migrate.sh:ro',
                   '-v', f'{ROOT}/docker/datahub/initdb.sh:/docker-entrypoint-initdb.d/initdb.sh:ro',
                   'postgres:18')
        cls.addClassCleanup(lambda: cls.docker('rm', '-f', cls.name))
        result = cls.docker('exec', cls.name, 'bash', '-c',
                           'for i in {1..60}; do '
                           'pg_isready -h 127.0.0.1 -U registry_test -d registry_test >/dev/null && '
                           'psql -U registry_test -d registry_test -Atc "SELECT count(*) FROM schema_migrations" '
                           '2>/dev/null | grep -qx 3 && exit 0; sleep 1; done; exit 1', check=False)
        if result.returncode:
            raise RuntimeError(cls.docker('logs', cls.name).stdout + cls.docker('logs', cls.name).stderr)

    def sql(self, sql, check=True, db='registry_test'):
        return self.docker('exec', '-i', self.name, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                           '-U', 'registry_test', '-d', db, '-At', input=sql, check=check)

    def claim(self, h, instance='test', db='registry_test'):
        return self.sql(f"SELECT * FROM crawler_claim('{h}', 'source/file.csv.gz', 100, 'test', '{instance}');", db=db).stdout.strip().split('|')

    def test_schema(self):
        tables = self.sql("SELECT tablename FROM pg_tables WHERE schemaname='public';").stdout.splitlines()
        for name in ('schema_migrations','collections','contributors','tokens','facebook','instagram',
                     'facebook_invalid','instagram_invalid','vkontakte','vkontakte_invalid',
                     'crawler_files','crawler_file_attempts','facebook_gb','instagram_us'):
            self.assertIn(name, tables)
        cols = self.sql("SELECT column_name FROM information_schema.columns WHERE table_name='crawler_file_attempts';").stdout.splitlines()
        for col in ('file_id','archive_sha256','archive_size','relative_path','collection','crawler_instance',
                    'api_version','completion_policy_version','retry_of','claim_token','started_at',
                    'lease_expires_at','finished_at','outcome','total_rows','rows_200','rows_409',
                    'rows_400','accepted_400','rows_401','rows_5xx','rows_other','corrupt_rows','error_summary',
                    'attempt_mode','contributor_id','client_request_id','start_decision'):
            self.assertIn(col, cols)
        indexes = self.sql("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'crawler_%';").stdout
        for index in ('crawler_one_active_claim','crawler_attempt_history','crawler_expiring_claims',
                      'crawler_recent_outcomes','crawler_files_content_sha256_key'):
            self.assertIn(index, indexes)
        self.assertGreater(int(self.sql("SELECT count(*) FROM pg_constraint WHERE conrelid='crawler_file_attempts'::regclass;").stdout), 15)
        for path in ('/absolute.csv','../escape.csv','a/../escape.csv','a//b','C:/file.csv','a\\b'):
            self.assertNotEqual(self.sql(f"SELECT '{path}'::crawler_relative_path;", check=False).returncode, 0)
        self.assertNotEqual(self.sql("SELECT 'invalid'::crawler_sha256;", check=False).returncode, 0)

    def test_four_claimers_and_completion(self):
        h = 'a' * 64
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: self.claim(h, f'replica-{i}'), range(4)))
        self.assertEqual(sorted(r[0] for r in results), ['in_progress'] * 3 + ['process'])
        _, aid, token = next(r for r in results if r[0] == 'process')
        self.assertNotEqual(self.sql(f"SELECT crawler_finish({aid},'{token}','completed',2,1);", check=False).returncode, 0)
        self.assertEqual(self.sql(f"SELECT crawler_finish({aid},gen_random_uuid(),'completed',2,1,1);").stdout.strip(), 'f')
        self.assertEqual(self.sql(f"SET ROLE writer; SELECT crawler_finish({aid},'{token}','completed',2,1,1);").stdout.splitlines()[-1], 't')
        self.assertEqual(self.claim(h)[0], 'already_completed')
        self.assertEqual(self.sql(f"SELECT crawler_finish({aid},'{token}','failed',2);").stdout.strip(), 'f')

    def test_expiry_failure_and_corruption_are_retryable(self):
        h = 'b' * 64
        _, aid, token = self.claim(h)
        self.sql(f"UPDATE crawler_file_attempts SET started_at=clock_timestamp()-interval '2 hours', lease_expires_at=clock_timestamp()-interval '1 hour' WHERE id={aid};")
        self.assertEqual(self.sql(f"SELECT crawler_finish({aid},'{token}','completed',0);").stdout.strip(), 'f')
        decision, next_id, next_token = self.claim(h)
        self.assertEqual(decision, 'retry')
        self.assertEqual(self.sql(f"SELECT outcome FROM crawler_file_attempts WHERE id={aid};").stdout.strip(), 'abandoned')
        self.assertEqual(self.sql(f"SELECT retry_of FROM crawler_file_attempts WHERE id={next_id};").stdout.strip(), aid)
        for column in ('rows_400','rows_401','rows_5xx','rows_other','corrupt_rows'):
            self.assertNotEqual(self.sql(f"UPDATE crawler_file_attempts SET outcome='completed', finished_at=clock_timestamp(),total_rows=1,{column}=1 WHERE id={next_id};", check=False).returncode, 0)
        self.sql(f"SELECT crawler_finish({next_id},'{next_token}','failed',3,0,0,1,1,1);")
        decision, next_id, next_token = self.claim(h)
        self.assertEqual(decision, 'retry')
        self.sql(f"SELECT crawler_finish({next_id},'{next_token}','corrupt',NULL,0,0,0,0,0,0,1);")
        self.assertEqual(self.claim(h)[0], 'retry')

    def test_observations_do_not_block_enforced_claims(self):
        h = 'd' * 64
        observe_request = '123e4567-e89b-12d3-a456-426614174000'
        observed_result = self.sql(
            f"SELECT * FROM crawler_observe_v2('{h}','source/file.csv.gz',100,'test','observer',1,'{observe_request}');",
            check=False,
        )
        self.assertEqual(observed_result.returncode, 0, observed_result.stderr)
        observed = observed_result.stdout.strip().split('|')
        self.assertEqual(observed[0], 'observe')
        self.assertEqual(observed[3], '')
        # Lost-response replay uses the same attempt rather than creating another observation.
        self.assertEqual(self.sql(
            f"SELECT * FROM crawler_observe_v2('{h}','source/file.csv.gz',100,'test','observer',1,'{observe_request}');"
        ).stdout.strip().split('|')[1], observed[1])
        claimed = self.sql(
            f"SELECT * FROM crawler_claim_v2('{h}','source/file.csv.gz',100,'test','crawler',1,"
            "'223e4567-e89b-12d3-a456-426614174000');"
        ).stdout.strip().split('|')
        self.assertEqual(claimed[0], 'process')
        self.assertEqual(self.sql(
            f"SELECT crawler_finish_v2({observed[1]},'{observed[2]}',1,'completed',1,1);"
        ).stdout.strip(), 't')
        # An observed completion is not authoritative for enforced claim decisions.
        self.assertEqual(self.sql(
            f"SELECT crawler_renew_v2({claimed[1]},'{claimed[2]}',1,60) IS NOT NULL;"
        ).stdout.strip(), 't')
        self.assertEqual(self.sql(
            f"SELECT crawler_finish_v2({claimed[1]},'{claimed[2]}',1,'completed',1,1);"
        ).stdout.strip(), 't')
        self.assertEqual(self.sql(
            f"SELECT * FROM crawler_claim_v2('{h}','source/file.csv.gz',100,'test','crawler',1,"
            "'323e4567-e89b-12d3-a456-426614174000');"
        ).stdout.strip().split('|')[0], 'already_completed')

    def test_transactional_rollback_and_concurrent_migrations(self):
        self.sql('CREATE DATABASE migration_failure_test;')
        self.docker('exec', self.name, 'bash', '-c',
                    'cp -r /schema /tmp/broken-schema && '
                    "printf '%s\\n' 'CREATE TABLE should_roll_back(id integer);' "
                    "'SELECT nonexistent_function();' > /tmp/broken-schema/migrations/0003_failure.sql")
        result = self.docker('exec', '-e', 'POSTGRES_DB=migration_failure_test', self.name,
                             'bash', '/tmp/broken-schema/migrate.sh', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';",
                                  db='migration_failure_test').stdout.strip(), '0')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.docker('exec', '-e',
                'POSTGRES_DB=migration_failure_test', self.name, 'bash', '/schema/migrate.sh'), range(2)))
        self.assertTrue(all(r.returncode == 0 for r in results))
        self.assertEqual(self.sql('SELECT count(*) FROM schema_migrations;',
                                  db='migration_failure_test').stdout.strip(), '3')

    def test_migration_rerun_and_legacy_upgrade(self):
        self.docker('exec', self.name, 'bash', '/schema/migrate.sh')
        self.assertEqual(self.sql('SELECT count(*) FROM schema_migrations;').stdout.strip(), '3')
        self.sql('CREATE DATABASE legacy_test;')
        baseline = (ROOT / 'docker/datahub/migrations/0001_initial.sql').read_text()
        self.sql(baseline, db='legacy_test')
        self.docker('exec', '-e', 'POSTGRES_DB=legacy_test', self.name, 'bash', '/schema/migrate.sh', '--baseline-legacy')
        # Both paths must produce identical columns, constraints, indexes and partitions.
        for query in (
            "SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2;",
            "SELECT conrelid::regclass,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1::text,2;",
            "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2;",
        ):
            self.assertEqual(sorted(self.sql(query).stdout.splitlines()),
                             sorted(self.sql(query, db='legacy_test').stdout.splitlines()))
        self.assertEqual(self.claim('c' * 64, db='legacy_test')[0], 'process')
        self.assertEqual(self.sql('SELECT count(*) FROM schema_migrations;', db='legacy_test').stdout.strip(), '3')
        # Applied SQL is immutable; mismatch must fail without replacing the ledger.
        self.sql("UPDATE schema_migrations SET checksum=repeat('0',64) WHERE version='0002_crawler_file_registry';", db='legacy_test')
        result = self.docker('exec', '-e', 'POSTGRES_DB=legacy_test', self.name, 'bash', '/schema/migrate.sh', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
