-- raw_entities now created+renamed by 003_three_layer. This migration is a no-op
-- kept for ordering; indexes on raw moved to 003 to stay idempotent across re-runs.
-- ponytail: original 001 created canonical_entities(payload); 003 renames it to
-- raw_entities and creates a new canonical_entities without payload. Re-running
-- 001's payload index on the new canonical table fails (no payload col), so we
-- move raw indexes into 003 and void 001.
SELECT 1;
