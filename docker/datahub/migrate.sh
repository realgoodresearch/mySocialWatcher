#!/usr/bin/env bash
# Explicit connection parameters; never source a production .env file.
set -euo pipefail
: "${POSTGRES_USER:?Set POSTGRES_USER explicitly}"
: "${POSTGRES_DB:?Set POSTGRES_DB explicitly}"
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
legacy=false
if [[ ${1:-} == --baseline-legacy ]]; then legacy=true; shift; fi
if (( $# )); then echo 'Usage: migrate.sh [--baseline-legacy]' >&2; exit 2; fi
# One session and transaction: concurrent runners serialize; failures roll back all changes.
{
cat <<'SQL'
\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(536870905);
CREATE TABLE IF NOT EXISTS schema_migrations (
 version text PRIMARY KEY,
 checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
SQL
for file in "$root"/migrations/[0-9]*.sql; do
 version=$(basename "$file" .sql)
 checksum=$(sha256sum "$file" | cut -d ' ' -f1)
 cat <<SQL
SELECT NOT EXISTS (SELECT FROM schema_migrations WHERE version = '$version') AS pending \gset
DO \$check\$ BEGIN
 IF EXISTS (SELECT FROM schema_migrations WHERE version = '$version' AND checksum <> '$checksum') THEN
  RAISE EXCEPTION 'Migration checksum mismatch: $version';
 END IF;
END \$check\$;
\if :pending
SQL
 if $legacy && [[ $version == 0001_initial ]]; then
 cat <<'SQL'
-- Adoption is explicit; refuse empty or clearly incomplete legacy installations.
DO $$ BEGIN
 IF EXISTS (SELECT FROM unnest(ARRAY['collections','contributors','tokens','facebook',
 'facebook_invalid','instagram','instagram_invalid','vkontakte','vkontakte_invalid']) t(name)
 WHERE to_regclass('public.' || name) IS NULL) THEN
  RAISE EXCEPTION 'Legacy baseline requires the complete existing datahub schema';
 END IF;
END $$;
SQL
 else
 cat "$file"
 fi
 printf "\nINSERT INTO schema_migrations(version, checksum) VALUES ('%s', '%s');\n" "$version" "$checksum"
 printf '%s\n' '\endif'
done
printf 'COMMIT;\n'
} | psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
