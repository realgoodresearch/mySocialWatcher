-- Paths are POSIX paths relative to data/. Content identity is decompressed bytes.
CREATE DOMAIN crawler_relative_path AS text CHECK (
 VALUE <> '' AND VALUE !~ '(^/|(^|/)\.\.?(/|$)|//|\\|^[A-Za-z]:)' AND VALUE !~ '/$'
);
CREATE DOMAIN crawler_sha256 AS text CHECK (VALUE ~ '^[0-9a-f]{64}$');

CREATE TABLE crawler_files (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 content_sha256 crawler_sha256 NOT NULL UNIQUE,
 original_path crawler_relative_path NOT NULL,
 uncompressed_size bigint NOT NULL CHECK (uncompressed_size >= 0),
 first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE crawler_file_attempts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 file_id bigint NOT NULL REFERENCES crawler_files(id),
 relative_path crawler_relative_path NOT NULL,
 archive_sha256 crawler_sha256,
 archive_size bigint CHECK (archive_size >= 0),
 collection text NOT NULL CHECK (collection <> ''),
 crawler_instance text NOT NULL CHECK (crawler_instance <> ''),
 api_version text NOT NULL CHECK (api_version <> ''),
 completion_policy_version text NOT NULL CHECK (completion_policy_version <> ''),
 retry_of bigint,
 claim_token uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease_expires_at timestamptz NOT NULL,
 finished_at timestamptz,
 outcome text NOT NULL DEFAULT 'claimed' CHECK (outcome IN
  ('claimed','completed','completed_with_rejections','failed','corrupt','abandoned')),
 total_rows bigint CHECK (total_rows >= 0),
 rows_200 bigint NOT NULL DEFAULT 0 CHECK (rows_200 >= 0),
 rows_409 bigint NOT NULL DEFAULT 0 CHECK (rows_409 >= 0),
 rows_400 bigint NOT NULL DEFAULT 0 CHECK (rows_400 >= 0),
 accepted_400 bigint NOT NULL DEFAULT 0 CHECK (accepted_400 BETWEEN 0 AND rows_400),
 rows_401 bigint NOT NULL DEFAULT 0 CHECK (rows_401 >= 0),
 rows_5xx bigint NOT NULL DEFAULT 0 CHECK (rows_5xx >= 0),
 rows_other bigint NOT NULL DEFAULT 0 CHECK (rows_other >= 0),
 corrupt_rows bigint NOT NULL DEFAULT 0 CHECK (corrupt_rows >= 0),
 error_summary varchar(1000),
 UNIQUE (file_id, id),
 FOREIGN KEY (file_id, retry_of) REFERENCES crawler_file_attempts(file_id, id),
 CHECK (retry_of IS NULL OR retry_of < id),
 CHECK (lease_expires_at > started_at),
 CHECK ((outcome = 'claimed') = (finished_at IS NULL)),
 CHECK (finished_at IS NULL OR finished_at >= started_at),
 CHECK (total_rows IS NULL OR rows_200::numeric + rows_409 + rows_400 + rows_401 + rows_5xx + rows_other + corrupt_rows <= total_rows),
 CONSTRAINT crawler_terminal_completion CHECK (
  outcome NOT IN ('completed','completed_with_rejections') OR
  (total_rows IS NOT NULL AND total_rows = rows_200::numeric + rows_409 + accepted_400
   AND rows_400 = accepted_400 AND rows_401 = 0 AND rows_5xx = 0
   AND rows_other = 0 AND corrupt_rows = 0
   AND ((outcome = 'completed') = (accepted_400 = 0)))
 ),
 -- Policy v1 accepts only inserted/duplicate rows. Future accepted 400 categories
 -- require a reviewed migration and API policy implementation, not a caller flag.
 CONSTRAINT crawler_policy_v1 CHECK (completion_policy_version = 'v1' AND accepted_400 = 0)
);
CREATE UNIQUE INDEX crawler_one_active_claim ON crawler_file_attempts(file_id) WHERE outcome = 'claimed';
CREATE INDEX crawler_attempt_history ON crawler_file_attempts(file_id, started_at DESC);
CREATE INDEX crawler_expiring_claims ON crawler_file_attempts(lease_expires_at) WHERE outcome = 'claimed';
CREATE INDEX crawler_recent_outcomes ON crawler_file_attempts(outcome, started_at DESC);

-- All claimers lock the unique logical file, including when expiring stale claims.
CREATE FUNCTION crawler_claim(p_hash text, p_path text, p_size bigint,
 p_collection text, p_instance text, p_lease_seconds integer DEFAULT 900)
RETURNS TABLE(decision text, attempt_id bigint, lease_token uuid) LANGUAGE plpgsql AS $$
DECLARE f bigint; previous bigint; a crawler_file_attempts; now_at timestamptz;
BEGIN
 IF p_lease_seconds NOT BETWEEN 1 AND 86400 OR p_lease_seconds IS NULL THEN
  RAISE EXCEPTION 'Lease must be between 1 and 86400 seconds';
 END IF;
 INSERT INTO crawler_files(content_sha256, original_path, uncompressed_size)
 VALUES (p_hash, p_path, p_size) ON CONFLICT (content_sha256) DO NOTHING;
 SELECT id INTO f FROM crawler_files WHERE content_sha256 = p_hash FOR UPDATE;
 IF (SELECT uncompressed_size FROM crawler_files WHERE id = f) <> p_size THEN
  RAISE EXCEPTION 'Content size mismatch';
 END IF;
 now_at := clock_timestamp();
 IF EXISTS (SELECT FROM crawler_file_attempts WHERE file_id = f AND outcome IN ('completed','completed_with_rejections')) THEN
  RETURN QUERY SELECT 'already_completed'::text, NULL::bigint, NULL::uuid; RETURN;
 END IF;
 SELECT * INTO a FROM crawler_file_attempts WHERE file_id = f AND outcome = 'claimed';
 IF FOUND AND a.lease_expires_at > now_at THEN
  RETURN QUERY SELECT 'in_progress'::text, NULL::bigint, NULL::uuid; RETURN;
 END IF;
 UPDATE crawler_file_attempts SET outcome = 'abandoned', finished_at = now_at
 WHERE file_id = f AND outcome = 'claimed';
 SELECT id INTO previous FROM crawler_file_attempts WHERE file_id = f ORDER BY id DESC LIMIT 1;
 INSERT INTO crawler_file_attempts(file_id, relative_path, collection, crawler_instance,
 api_version, completion_policy_version, retry_of, started_at, lease_expires_at)
 VALUES (f, p_path, p_collection, p_instance, 'v2', 'v1', previous, now_at,
 now_at + make_interval(secs => p_lease_seconds)) RETURNING * INTO a;
 RETURN QUERY SELECT CASE WHEN previous IS NULL THEN 'process' ELSE 'retry' END, a.id, a.claim_token;
END $$;

CREATE FUNCTION crawler_finish(p_id bigint, p_token uuid, p_outcome text, p_total bigint,
 p_200 bigint DEFAULT 0, p_409 bigint DEFAULT 0, p_400 bigint DEFAULT 0,
 p_401 bigint DEFAULT 0, p_5xx bigint DEFAULT 0, p_other bigint DEFAULT 0,
 p_corrupt bigint DEFAULT 0, p_error text DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE f bigint;
BEGIN
 SELECT file_id INTO f FROM crawler_file_attempts WHERE id = p_id;
 PERFORM id FROM crawler_files WHERE id = f FOR UPDATE;
 IF p_outcome NOT IN ('completed','failed','corrupt','abandoned') OR p_outcome IS NULL THEN
  RAISE EXCEPTION 'Invalid finish outcome';
 END IF;
 UPDATE crawler_file_attempts SET outcome = p_outcome, finished_at = clock_timestamp(),
 total_rows = p_total, rows_200 = p_200, rows_409 = p_409, rows_400 = p_400,
 rows_401 = p_401, rows_5xx = p_5xx, rows_other = p_other,
 corrupt_rows = p_corrupt, error_summary = p_error
 WHERE id = p_id AND claim_token = p_token AND outcome = 'claimed'
 AND lease_expires_at > clock_timestamp();
 RETURN FOUND;
END $$;

GRANT SELECT ON crawler_files, crawler_file_attempts TO reader, writer;
GRANT INSERT, UPDATE ON crawler_files, crawler_file_attempts TO writer;
GRANT USAGE, SELECT ON SEQUENCE crawler_files_id_seq, crawler_file_attempts_id_seq TO writer;
REVOKE ALL ON FUNCTION crawler_claim(text,text,bigint,text,text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION crawler_finish(bigint,uuid,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION crawler_claim(text,text,bigint,text,text,integer) TO writer;
GRANT EXECUTE ON FUNCTION crawler_finish(bigint,uuid,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text) TO writer;
