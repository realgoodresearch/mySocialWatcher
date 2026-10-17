-- Observation records are diagnostic only. They never block an enforced claim
-- and are never considered by crawler_claim when deciding completion.
ALTER TABLE crawler_file_attempts
  ADD COLUMN attempt_mode text NOT NULL DEFAULT 'enforce'
    CHECK (attempt_mode IN ('enforce', 'observe')),
  ADD COLUMN contributor_id integer REFERENCES contributors(id),
  ADD COLUMN client_request_id uuid,
  ADD COLUMN start_decision text CHECK (start_decision IN ('observe', 'process', 'retry'));

DO $$
DECLARE constraint_name text;
BEGIN
  SELECT conname INTO constraint_name
  FROM pg_constraint
  WHERE conrelid = 'crawler_file_attempts'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%lease_expires_at > started_at%';
  EXECUTE format('ALTER TABLE crawler_file_attempts DROP CONSTRAINT %I', constraint_name);
END $$;

ALTER TABLE crawler_file_attempts
  ALTER COLUMN lease_expires_at DROP NOT NULL;

ALTER TABLE crawler_file_attempts
  ADD CONSTRAINT crawler_attempt_lease_mode CHECK (
    (attempt_mode = 'enforce' AND lease_expires_at IS NOT NULL AND lease_expires_at > started_at)
    OR (attempt_mode = 'observe' AND lease_expires_at IS NULL)
  );

DROP INDEX crawler_one_active_claim;
CREATE UNIQUE INDEX crawler_one_active_claim ON crawler_file_attempts(file_id)
  WHERE attempt_mode = 'enforce' AND outcome = 'claimed';
CREATE UNIQUE INDEX crawler_attempt_request_id ON crawler_file_attempts
  (contributor_id, attempt_mode, client_request_id)
  WHERE contributor_id IS NOT NULL AND client_request_id IS NOT NULL;
CREATE INDEX crawler_attempt_owner ON crawler_file_attempts(contributor_id, id DESC)
  WHERE contributor_id IS NOT NULL;

CREATE FUNCTION crawler_observe_v2(
  p_hash text, p_path text, p_size bigint, p_collection text, p_instance text,
  p_contributor_id integer, p_request_id uuid, p_archive_hash text DEFAULT NULL,
  p_archive_size bigint DEFAULT NULL
) RETURNS TABLE(decision text, attempt_id bigint, attempt_token uuid, lease_expires_at timestamptz)
LANGUAGE plpgsql AS $$
DECLARE f bigint; a crawler_file_attempts;
BEGIN
  INSERT INTO crawler_files(content_sha256, original_path, uncompressed_size)
  VALUES (p_hash, p_path, p_size) ON CONFLICT (content_sha256) DO NOTHING;
  SELECT id INTO f FROM crawler_files WHERE content_sha256 = p_hash FOR UPDATE;
  IF (SELECT uncompressed_size FROM crawler_files WHERE id = f) <> p_size THEN
    RAISE EXCEPTION 'Content size mismatch';
  END IF;
  SELECT * INTO a FROM crawler_file_attempts
    WHERE contributor_id = p_contributor_id AND attempt_mode = 'observe'
      AND client_request_id = p_request_id;
  IF FOUND THEN
    RETURN QUERY SELECT a.start_decision, a.id, a.claim_token, a.lease_expires_at;
    RETURN;
  END IF;
  INSERT INTO crawler_file_attempts(
    file_id, relative_path, archive_sha256, archive_size, collection, crawler_instance,
    api_version, completion_policy_version, attempt_mode, contributor_id,
    client_request_id, start_decision, lease_expires_at
  ) VALUES (
    f, p_path, p_archive_hash, p_archive_size, p_collection, p_instance,
    'v2', 'v1', 'observe', p_contributor_id, p_request_id, 'observe', NULL
  ) RETURNING * INTO a;
  RETURN QUERY SELECT 'observe'::text, a.id, a.claim_token, a.lease_expires_at;
END $$;

CREATE FUNCTION crawler_claim_v2(
  p_hash text, p_path text, p_size bigint, p_collection text, p_instance text,
  p_contributor_id integer, p_request_id uuid, p_lease_seconds integer DEFAULT 900,
  p_archive_hash text DEFAULT NULL, p_archive_size bigint DEFAULT NULL
) RETURNS TABLE(decision text, attempt_id bigint, attempt_token uuid, lease_expires_at timestamptz)
LANGUAGE plpgsql AS $$
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
  SELECT * INTO a FROM crawler_file_attempts
    WHERE contributor_id = p_contributor_id AND attempt_mode = 'enforce'
      AND client_request_id = p_request_id;
  IF FOUND THEN
    RETURN QUERY SELECT a.start_decision, a.id, a.claim_token, a.lease_expires_at;
    RETURN;
  END IF;
  now_at := clock_timestamp();
  IF EXISTS (SELECT FROM crawler_file_attempts WHERE file_id = f AND attempt_mode = 'enforce'
             AND outcome IN ('completed', 'completed_with_rejections')) THEN
    RETURN QUERY SELECT 'already_completed'::text, NULL::bigint, NULL::uuid, NULL::timestamptz;
    RETURN;
  END IF;
  SELECT * INTO a FROM crawler_file_attempts WHERE file_id = f AND attempt_mode = 'enforce' AND outcome = 'claimed';
  IF FOUND AND a.lease_expires_at > now_at THEN
    RETURN QUERY SELECT 'in_progress'::text, NULL::bigint, NULL::uuid, a.lease_expires_at;
    RETURN;
  END IF;
  UPDATE crawler_file_attempts SET outcome = 'abandoned', finished_at = now_at
    WHERE file_id = f AND attempt_mode = 'enforce' AND outcome = 'claimed';
  SELECT id INTO previous FROM crawler_file_attempts WHERE file_id = f AND attempt_mode = 'enforce'
    ORDER BY id DESC LIMIT 1;
  INSERT INTO crawler_file_attempts(
    file_id, relative_path, archive_sha256, archive_size, collection, crawler_instance,
    api_version, completion_policy_version, attempt_mode, contributor_id, client_request_id,
    start_decision, retry_of, started_at, lease_expires_at
  ) VALUES (
    f, p_path, p_archive_hash, p_archive_size, p_collection, p_instance,
    'v2', 'v1', 'enforce', p_contributor_id, p_request_id,
    CASE WHEN previous IS NULL THEN 'process' ELSE 'retry' END, previous, now_at,
    now_at + make_interval(secs => p_lease_seconds)
  ) RETURNING * INTO a;
  RETURN QUERY SELECT a.start_decision, a.id, a.claim_token, a.lease_expires_at;
END $$;

CREATE FUNCTION crawler_renew_v2(p_id bigint, p_token uuid, p_contributor_id integer,
  p_lease_seconds integer DEFAULT 900)
RETURNS timestamptz LANGUAGE plpgsql AS $$
DECLARE f bigint; expires timestamptz;
BEGIN
  IF p_lease_seconds NOT BETWEEN 1 AND 86400 OR p_lease_seconds IS NULL THEN
    RAISE EXCEPTION 'Lease must be between 1 and 86400 seconds';
  END IF;
  SELECT file_id INTO f FROM crawler_file_attempts WHERE id = p_id;
  PERFORM id FROM crawler_files WHERE id = f FOR UPDATE;
  UPDATE crawler_file_attempts SET lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
    WHERE id = p_id AND claim_token = p_token AND contributor_id = p_contributor_id
      AND attempt_mode = 'enforce' AND outcome = 'claimed' AND lease_expires_at > clock_timestamp()
    RETURNING lease_expires_at INTO expires;
  RETURN expires;
END $$;

CREATE FUNCTION crawler_finish_v2(
  p_id bigint, p_token uuid, p_contributor_id integer, p_outcome text, p_total bigint,
  p_200 bigint DEFAULT 0, p_409 bigint DEFAULT 0, p_400 bigint DEFAULT 0,
  p_401 bigint DEFAULT 0, p_5xx bigint DEFAULT 0, p_other bigint DEFAULT 0,
  p_corrupt bigint DEFAULT 0, p_error text DEFAULT NULL
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE f bigint; mode text;
BEGIN
  SELECT file_id, attempt_mode INTO f, mode FROM crawler_file_attempts WHERE id = p_id;
  PERFORM id FROM crawler_files WHERE id = f FOR UPDATE;
  IF p_outcome NOT IN ('completed', 'failed', 'corrupt', 'abandoned') OR p_outcome IS NULL THEN
    RAISE EXCEPTION 'Invalid finish outcome';
  END IF;
  UPDATE crawler_file_attempts SET outcome = p_outcome, finished_at = clock_timestamp(),
    total_rows = p_total, rows_200 = p_200, rows_409 = p_409, rows_400 = p_400,
    rows_401 = p_401, rows_5xx = p_5xx, rows_other = p_other,
    corrupt_rows = p_corrupt, error_summary = p_error
    WHERE id = p_id AND claim_token = p_token AND contributor_id = p_contributor_id
      AND outcome = 'claimed' AND (mode = 'observe' OR lease_expires_at > clock_timestamp());
  RETURN FOUND;
END $$;

REVOKE ALL ON FUNCTION crawler_observe_v2(text,text,bigint,text,text,integer,uuid,text,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION crawler_claim_v2(text,text,bigint,text,text,integer,uuid,integer,text,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION crawler_renew_v2(bigint,uuid,integer,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION crawler_finish_v2(bigint,uuid,integer,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION crawler_observe_v2(text,text,bigint,text,text,integer,uuid,text,bigint) TO writer;
GRANT EXECUTE ON FUNCTION crawler_claim_v2(text,text,bigint,text,text,integer,uuid,integer,text,bigint) TO writer;
GRANT EXECUTE ON FUNCTION crawler_renew_v2(bigint,uuid,integer,integer) TO writer;
GRANT EXECUTE ON FUNCTION crawler_finish_v2(bigint,uuid,integer,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text) TO writer;
