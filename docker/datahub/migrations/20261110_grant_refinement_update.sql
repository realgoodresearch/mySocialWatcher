-- Allow API v2 to promote an original audience row with refined measurements.
-- The grant is intentionally limited to the columns changed by the conflict policy.
GRANT UPDATE (mau, mau_lower, mau_upper, all_fields) ON facebook TO writer;
GRANT UPDATE (mau, mau_lower, mau_upper, all_fields) ON facebook_invalid TO writer;
GRANT UPDATE (mau, mau_lower, mau_upper, all_fields) ON instagram TO writer;
GRANT UPDATE (mau, mau_lower, mau_upper, all_fields) ON instagram_invalid TO writer;
