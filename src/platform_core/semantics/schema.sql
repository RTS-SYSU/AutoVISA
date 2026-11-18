-- Semantic drafts reference immutable PDF extraction snapshots.
CREATE TABLE IF NOT EXISTS semantic_snapshots (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'), -- Whole semantic manifest address.
    extraction_id text NOT NULL REFERENCES paper_extractions(id),
    source_sha256 text NOT NULL REFERENCES paper_sources(sha256),
    profile_sha256 text NOT NULL, -- Identities of rules, code and project choices.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS semantic_snapshots_extraction ON semantic_snapshots(extraction_id);
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='semantic_snapshots'::regclass AND tgname='immutable') THEN
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON semantic_snapshots
        FOR EACH STATEMENT EXECUTE FUNCTION reject_edit();
    END IF;
END $$;
