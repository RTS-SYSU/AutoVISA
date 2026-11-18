-- MSA projects carry user-authored semantics without a mandatory paper foreign key.
CREATE TABLE IF NOT EXISTS msa_projects (
    id text PRIMARY KEY,
    name text NOT NULL,
    original text NOT NULL, -- Content address of the untouched import or blank input.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS msa_revisions (
    id text PRIMARY KEY, -- Content address of the revision, actor and exact differences.
    project text NOT NULL REFERENCES msa_projects(id),
    parent text REFERENCES msa_revisions(id),
    generation integer NOT NULL CHECK(generation > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(project,generation)
);
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='msa_projects'::regclass AND tgname='immutable') THEN
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON msa_projects
            FOR EACH STATEMENT EXECUTE FUNCTION reject_edit();
    END IF;
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='msa_revisions'::regclass AND tgname='immutable') THEN
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON msa_revisions
            FOR EACH STATEMENT EXECUTE FUNCTION reject_edit();
    END IF;
END $$;

-- Frozen review and mapping/proof records are distinct from mutable project heads.
CREATE TABLE IF NOT EXISTS msa_freezes (
    id text PRIMARY KEY,
    project text NOT NULL REFERENCES msa_projects(id),
    revision text NOT NULL UNIQUE REFERENCES msa_revisions(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS msa_results (
    id text PRIMARY KEY,
    freeze_id text NOT NULL REFERENCES msa_freezes(id),
    kind text NOT NULL CHECK(kind IN ('mapping','proof')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE table_name text; -- Current immutable artifact family.
BEGIN
    FOREACH table_name IN ARRAY ARRAY['msa_freezes','msa_results'] LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=table_name::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I
                FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()',table_name);
        END IF;
    END LOOP;
END $$;

-- Immutable attachment to an imported PDF; semantic content still belongs to reviewed revisions.
CREATE TABLE IF NOT EXISTS msa_papers(
    project text PRIMARY KEY REFERENCES msa_projects(id),
    extraction text NOT NULL
);
DROP TRIGGER IF EXISTS msa_papers_immutable ON msa_papers;
CREATE TRIGGER msa_papers_immutable BEFORE UPDATE OR DELETE ON msa_papers
    FOR EACH ROW EXECUTE FUNCTION reject_edit();
