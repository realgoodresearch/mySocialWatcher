#!/usr/bin/env bash
# Create one verified logical PostgreSQL backup for Borg to archive.
set -Eeuo pipefail
umask 077

backup_root=${BACKUP_ROOT:-/home/backup/socialwatcher}
database_container=${DATABASE_CONTAINER:-datahub_db}
database_name=${POSTGRES_DB:-social_media_audience}
database_user=${POSTGRES_USER:-postgres}
backup_label=${BACKUP_LABEL:-routine}

usage() {
  cat <<'EOF'
Usage: utils/datahub_backup.sh [--label NAME]

Configuration is set with environment variables, for example:
  BACKUP_ROOT=/mnt/backups/socialwatcher utils/datahub_backup.sh
  DATABASE_CONTAINER=datahub_db_prod POSTGRES_DB=audience utils/datahub_backup.sh

Environment variables:
  BACKUP_ROOT         local destination (default: /home/backup/socialwatcher)
  DATABASE_CONTAINER  running PostgreSQL container (default: datahub_db)
  POSTGRES_DB         database to dump (default: social_media_audience)
  POSTGRES_USER       role used inside the container (default: postgres)
  BACKUP_LABEL        label, equivalent to --label (default: routine)

The default `routine` label removes older verified routine backups only after a
new backup is created and verified. Use another label, such as
`pre-migration-issue-5`, to retain a protected backup locally.
EOF
}

if [[ ${1:-} == --label ]]; then
  [[ $# == 2 ]] || { usage >&2; exit 2; }
  backup_label=$2
elif [[ $# != 0 ]]; then
  usage >&2
  exit 2
fi

[[ $backup_label =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]] || {
  printf 'Invalid backup label: %s\n' "$backup_label" >&2
  exit 2
}

mkdir -p "$backup_root"
exec 9>"$backup_root/.datahub-backup.lock"
flock -n 9 || { printf 'Another datahub backup is already running.\n' >&2; exit 1; }

timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
backup_name="$backup_label-$timestamp"
staging_dir=$(mktemp -d "$backup_root/.${backup_name}.staging.XXXXXX")
final_dir="$backup_root/$backup_name"
trap 'rm -rf "$staging_dir"' EXIT

printf 'Creating PostgreSQL custom archive for %s\n' "$database_name"
docker exec -i "$database_container" \
  pg_dump --username="$database_user" --format=custom "$database_name" \
  > "$staging_dir/database.dump"

printf 'Creating cluster globals archive\n'
docker exec -i "$database_container" \
  pg_dumpall --username="$database_user" --globals-only \
  > "$staging_dir/globals.sql"

[[ -s "$staging_dir/database.dump" ]] || { printf 'Database dump is empty.\n' >&2; exit 1; }
[[ -s "$staging_dir/globals.sql" ]] || { printf 'Globals dump is empty.\n' >&2; exit 1; }

printf 'Verifying PostgreSQL archive catalogue\n'
docker exec -i "$database_container" pg_restore --format=custom --list \
  < "$staging_dir/database.dump" > "$staging_dir/archive-contents.txt"
[[ -s "$staging_dir/archive-contents.txt" ]] || { printf 'Archive catalogue is empty.\n' >&2; exit 1; }

{
  printf 'backup_name=%s\n' "$backup_name"
  printf 'created_at_utc=%s\n' "$timestamp"
  printf 'database=%s\n' "$database_name"
  printf 'database_container=%s\n' "$database_container"
  printf 'pg_dump_version='
  docker exec -i "$database_container" pg_dump --version
  printf 'postgres_version='
  docker exec -i "$database_container" postgres --version
} > "$staging_dir/metadata.txt"

(cd "$staging_dir" && sha256sum database.dump globals.sql archive-contents.txt metadata.txt > checksums.sha256)
(cd "$staging_dir" && sha256sum --check checksums.sha256)

mv "$staging_dir" "$final_dir"
trap - EXIT
printf 'Verified backup published: %s\n' "$final_dir"

# Protected labels, including pre-migration backups, are never pruned here.
if [[ $backup_label == routine ]]; then
  while IFS= read -r -d '' old_backup; do
    printf 'Removing prior local routine backup: %s\n' "$old_backup"
    rm -rf "$old_backup"
  done < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name 'routine-*' \
             ! -path "$final_dir" -print0)
fi

printf 'Backup completed successfully. Borg can archive %s on its next run.\n' "$final_dir"
