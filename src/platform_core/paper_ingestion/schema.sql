-- Immutable source metadata and extraction manifests share W02's database and object store.
CREATE TABLE IF NOT EXISTS paper_sources (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_count bigint NOT NULL CHECK (byte_count > 0),
    first_filename text NOT NULL, -- Display metadata; it has no effect on content identity.
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS paper_extractions (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{64}$'), -- Also the manifest object address.
    source_sha256 text NOT NULL REFERENCES paper_sources(sha256),
    profile_sha256 text NOT NULL, -- Parser implementation, binary identities and settings.
    page_count integer NOT NULL CHECK (page_count > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS paper_extractions_source ON paper_extractions(source_sha256);
DO $$
DECLARE table_name text; -- Table receiving the same append-only protection as evidence history.
BEGIN
    FOREACH table_name IN ARRAY ARRAY['paper_sources', 'paper_extractions'] LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=table_name::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I
                            FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()', table_name);
        END IF;
    END LOOP;
END $$;
