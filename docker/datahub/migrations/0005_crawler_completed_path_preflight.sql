-- Make unchanged-path preflight checks cheap without changing content-hash identity.
CREATE INDEX crawler_completed_path_preflight
  ON crawler_file_attempts(contributor_id, relative_path, archive_size, finished_at DESC)
  WHERE attempt_mode = 'enforce'
    AND outcome IN ('completed', 'completed_with_rejections');
