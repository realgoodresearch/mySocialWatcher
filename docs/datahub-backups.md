# Datahub logical backups

`utils/backup/datahub_backup.sh` creates a verified PostgreSQL logical backup for the
existing Borg service to archive. Run it on the host that runs `datahub_db`:

```bash
utils/backup/datahub_backup.sh
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
utils/backup/datahub_backup.sh

# Different local destination
BACKUP_ROOT=/mnt/backup/socialwatcher utils/backup/datahub_backup.sh

# Different container, database, or database role
DATABASE_CONTAINER=datahub_db_prod POSTGRES_DB=audience POSTGRES_USER=backup \
  utils/backup/datahub_backup.sh
```

`BACKUP_ROOT`, `DATABASE_CONTAINER`, `POSTGRES_DB`, and `POSTGRES_USER` are the
supported configuration variables. They affect only the current invocation
unless you set them in the scheduler's environment.

Create a protected backup before a migration with a non-routine label:

```bash
utils/backup/datahub_backup.sh --label pre-migration-issue-5
```

Non-routine labels are never deleted by the script. Keep that directory until
the migration and follow-up validation are accepted.

The script does not configure Borg or change PostgreSQL. It creates a logical
dump only; it does not provide point-in-time recovery. Before relying on a new
backup procedure, restore an archive into a disposable PostgreSQL 18 instance:

```bash
utils/backup/datahub_restore.sh \
  --backup-dir /home/backup/socialwatcher/routine-... \
  --target-container disposable-postgres-18 \
  --yes-really-restore
```

The restore script verifies checksums before it drops and recreates the database
in the explicitly named target container. It never chooses a target container
by default. Add `--restore-globals` only in an isolated instance or with a
deliberate role-recovery plan, because `globals.sql` creates cluster-wide roles.

## Monthly systemd timer

Install the repository-managed units on the datahub host after the branch has
been deployed to `/home/doug/git/realgoodresearch/mySocialWatcher/`:

```bash
sudo cp utils/backup/systemd/socialwatcher-datahub-backup.service /etc/systemd/system/
sudo cp utils/backup/systemd/socialwatcher-datahub-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now socialwatcher-datahub-backup.timer
```

The timer runs monthly at 02:00 UTC with up to 15 minutes of jitter and records
output in the system journal. Schedule Borg after this window so it can capture
the newest local dump. Check the next scheduled run and the most recent result:

```bash
systemctl list-timers socialwatcher-datahub-backup.timer
journalctl -u socialwatcher-datahub-backup.service
```
