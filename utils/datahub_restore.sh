#!/usr/bin/env bash
# Restore a verified datahub logical backup into an explicitly named container.
set -Eeuo pipefail

backup_dir=
target_container=
database_user=${POSTGRES_USER:-postgres}
restore_globals=false
confirmed=false

usage() {
  cat <<'EOF'
Usage: utils/datahub_restore.sh --backup-dir DIRECTORY --target-container CONTAINER \
  --yes-really-restore [--restore-globals]

This verifies checksums before restoring. It drops and recreates the database in
the named target container. Use a disposable PostgreSQL 18 container unless a
production restore is explicitly intended. --restore-globals also applies the
cluster-wide roles in globals.sql and should normally be used only in isolation.
EOF
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --backup-dir) backup_dir=${2:-}; shift 2 ;;
    --target-container) target_container=${2:-}; shift 2 ;;
    --restore-globals) restore_globals=true; shift ;;
    --yes-really-restore) confirmed=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n $backup_dir && -n $target_container && $confirmed == true ]] || {
  usage >&2
  exit 2
}
[[ -d $backup_dir ]] || { printf 'Backup directory does not exist: %s\n' "$backup_dir" >&2; exit 2; }
for required_file in database.dump globals.sql checksums.sha256; do
  [[ -f "$backup_dir/$required_file" ]] || {
    printf 'Backup is missing %s\n' "$required_file" >&2
    exit 2
  }
done

printf 'Verifying backup checksums\n'
(cd "$backup_dir" && sha256sum --check checksums.sha256)

if [[ $restore_globals == true ]]; then
  printf 'Restoring cluster globals into %s\n' "$target_container"
  docker exec -i "$target_container" psql --username="$database_user" --dbname=postgres \
    -v ON_ERROR_STOP=1 < "$backup_dir/globals.sql"
fi

printf 'Restoring database archive into %s\n' "$target_container"
docker exec -i "$target_container" pg_restore --username="$database_user" --dbname=postgres \
  --format=custom --clean --if-exists --create --exit-on-error < "$backup_dir/database.dump"
printf 'Restore completed successfully.\n'
