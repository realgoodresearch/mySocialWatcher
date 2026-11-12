-- Record API v2 row actions so registry summaries match durable crawler logs.
ALTER TABLE crawler_file_attempts
  ADD COLUMN rows_inserted bigint NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
  ADD COLUMN rows_promoted bigint NOT NULL DEFAULT 0 CHECK (rows_promoted >= 0),
  ADD COLUMN rows_unchanged bigint NOT NULL DEFAULT 0 CHECK (rows_unchanged >= 0),
  ADD COLUMN rows_rejected bigint NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
  ADD CONSTRAINT crawler_action_totals CHECK (
    total_rows IS NULL OR
    rows_inserted::numeric + rows_promoted + rows_unchanged + rows_rejected <= total_rows
  );

ALTER TABLE crawler_file_attempts
  DROP CONSTRAINT crawler_terminal_completion,
  DROP CONSTRAINT crawler_policy_v1;

ALTER TABLE crawler_file_attempts
  ADD CONSTRAINT crawler_completion_policy CHECK (
    (completion_policy_version = 'v1' AND accepted_400 = 0)
    OR completion_policy_version = 'v2-actions'
  ),
  ADD CONSTRAINT crawler_terminal_completion CHECK (
    outcome NOT IN ('completed', 'completed_with_rejections') OR
    (total_rows IS NOT NULL AND rows_401 = 0 AND rows_5xx = 0
     AND rows_other = 0 AND corrupt_rows = 0
     AND (
       (completion_policy_version = 'v1'
        AND total_rows = rows_200::numeric + rows_409 + accepted_400
        AND rows_400 = accepted_400
        AND ((outcome = 'completed') = (accepted_400 = 0)))
       OR
       (completion_policy_version = 'v2-actions'
        AND total_rows = rows_inserted::numeric + rows_promoted
                         + rows_unchanged + rows_rejected
        AND rows_200 = rows_inserted + rows_promoted
        AND rows_409 = rows_unchanged
        AND rows_400 = rows_rejected
        AND ((outcome = 'completed') = (rows_rejected = 0)))
     ))
  );

DROP FUNCTION crawler_finish_v2(
  bigint, uuid, integer, text, bigint, bigint, bigint, bigint,
  bigint, bigint, bigint, bigint, text
);

CREATE FUNCTION crawler_finish_v2(
  p_id bigint, p_token uuid, p_contributor_id integer, p_outcome text, p_total bigint,
  p_200 bigint DEFAULT 0, p_409 bigint DEFAULT 0, p_400 bigint DEFAULT 0,
  p_401 bigint DEFAULT 0, p_5xx bigint DEFAULT 0, p_other bigint DEFAULT 0,
  p_corrupt bigint DEFAULT 0, p_error text DEFAULT NULL,
  p_inserted bigint DEFAULT 0, p_promoted bigint DEFAULT 0,
  p_unchanged bigint DEFAULT 0, p_rejected bigint DEFAULT 0
) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE f bigint; mode text;
BEGIN
  SELECT file_id, attempt_mode INTO f, mode FROM crawler_file_attempts WHERE id = p_id;
  PERFORM id FROM crawler_files WHERE id = f FOR UPDATE;
  IF p_outcome NOT IN (
    'completed', 'completed_with_rejections', 'failed', 'corrupt', 'abandoned'
  ) OR p_outcome IS NULL THEN
    RAISE EXCEPTION 'Invalid finish outcome';
  END IF;
  UPDATE crawler_file_attempts SET outcome = p_outcome, finished_at = clock_timestamp(),
    completion_policy_version = 'v2-actions',
    total_rows = p_total, rows_200 = p_200, rows_409 = p_409, rows_400 = p_400,
    rows_401 = p_401, rows_5xx = p_5xx, rows_other = p_other,
    corrupt_rows = p_corrupt, error_summary = p_error,
    rows_inserted = p_inserted, rows_promoted = p_promoted,
    rows_unchanged = p_unchanged, rows_rejected = p_rejected
    WHERE id = p_id AND claim_token = p_token AND contributor_id = p_contributor_id
      AND outcome = 'claimed' AND (mode = 'observe' OR lease_expires_at > clock_timestamp());
  RETURN FOUND;
END $$;

REVOKE ALL ON FUNCTION crawler_finish_v2(
  bigint,uuid,integer,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text,
  bigint,bigint,bigint,bigint
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION crawler_finish_v2(
  bigint,uuid,integer,text,bigint,bigint,bigint,bigint,bigint,bigint,bigint,bigint,text,
  bigint,bigint,bigint,bigint
) TO writer;
