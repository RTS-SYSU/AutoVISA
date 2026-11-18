-- Review history is separate from W02's typed propositions and proof receipts.
CREATE TABLE IF NOT EXISTS review_projects (
    id text PRIMARY KEY, -- Stable local workspace identity.
    name text NOT NULL,
    semantic_id text NOT NULL REFERENCES semantic_snapshots(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS review_revisions (
    id text PRIMARY KEY, -- Content address of the complete revision envelope.
    project text NOT NULL REFERENCES review_projects(id),
    parent text REFERENCES review_revisions(id),
    generation integer NOT NULL CHECK (generation > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(project, generation)
);
CREATE TABLE IF NOT EXISTS review_freezes (
    id text PRIMARY KEY, -- Content address of the frozen semantic context.
    project text NOT NULL REFERENCES review_projects(id),
    revision text NOT NULL UNIQUE REFERENCES review_revisions(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE table_name text; -- Each history table uses the existing append-only trigger.
BEGIN
    FOREACH table_name IN ARRAY ARRAY['review_projects','review_revisions','review_freezes'] LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=table_name::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I
                            FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()', table_name);
        END IF;
    END LOOP;
END $$;

