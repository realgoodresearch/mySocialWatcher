#!/usr/bin/env bash
set -euo pipefail
# Runs only during initialization of an empty PostgreSQL data directory.
psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --set=writer_password="$POSTGRES_WPASS" --set=reader_password="$POSTGRES_RPASS" <<'SQL'
CREATE ROLE writer LOGIN PASSWORD :'writer_password';
CREATE ROLE reader LOGIN PASSWORD :'reader_password';
SQL
bash /schema/migrate.sh
