-- Record when an existing audience row is promoted with refined estimates.
-- Existing rows remain NULL; PostgreSQL does not rewrite the tables.
ALTER TABLE facebook ADD COLUMN IF NOT EXISTS updated_on TIMESTAMPTZ(0);
ALTER TABLE facebook_invalid ADD COLUMN IF NOT EXISTS updated_on TIMESTAMPTZ(0);
ALTER TABLE instagram ADD COLUMN IF NOT EXISTS updated_on TIMESTAMPTZ(0);
ALTER TABLE instagram_invalid ADD COLUMN IF NOT EXISTS updated_on TIMESTAMPTZ(0);

GRANT UPDATE (updated_on) ON facebook TO writer;
GRANT UPDATE (updated_on) ON facebook_invalid TO writer;
GRANT UPDATE (updated_on) ON instagram TO writer;
GRANT UPDATE (updated_on) ON instagram_invalid TO writer;
