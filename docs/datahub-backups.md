# Datahub logical backups

`utils/datahub_backup.sh` creates a verified PostgreSQL logical backup for the
existing Borg service to archive. Run it on the host that runs `datahub_db`:

```bash
utils/datahub_backup.sh
```

It uses PostgreSQL 18 tools inside the running `datahub_db` container. The
default destination is `/home/backup/socialwatcher/`; set `BACKUP_ROOT` to use
another local staging location. A successful routine run creates a timestamped
directory containing a custom-format database archive, cluster globals, archive
catalogue, metadata, and SHA-256 checksums. It verifies the archive catalogue
before publishing it, then removes older directories named `routine-*`.

The previous local routine backup remains until the new backup has been verified
and atomically published. Borg's daily archive captures the historical sequence
before the next monthly run removes that prior local copy.

Configure it with environment variables preceding the command:

```bash
# Defaults: /home/backup/socialwatcher/, datahub_db, social_media_audience, postgres
utils/datahub_backup.sh

# Different local destination
BACKUP_ROOT=/mnt/backup/socialwatcher utils/datahub_backup.sh

# Different container, database, or database role
DATABASE_CONTAINER=datahub_db_prod POSTGRES_DB=audience POSTGRES_USER=backup \
  utils/datahub_backup.sh
```

`BACKUP_ROOT`, `DATABASE_CONTAINER`, `POSTGRES_DB`, and `POSTGRES_USER` are the
supported configuration variables. They affect only the current invocation
unless you set them in the scheduler's environment.

Create a protected backup before a migration with a non-routine label:

```bash
utils/datahub_backup.sh --label pre-migration-issue-5
```

Non-routine labels are never deleted by the script. Keep that directory until
the migration and follow-up validation are accepted.

The script does not configure Borg or change PostgreSQL. It creates a logical
dump only; it does not provide point-in-time recovery. Before relying on a new
backup procedure, restore an archive into a disposable PostgreSQL 18 instance:

```bash
pg_restore --clean --create --exit-on-error --dbname=postgres \
  /home/backup/socialwatcher/routine-.../database.dump
```

Restore `globals.sql` only in an isolated instance or with a deliberate role
recovery plan, because it creates cluster-wide roles.
