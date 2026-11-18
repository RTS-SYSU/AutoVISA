-- Feedback and proposals are append-only artifacts, separate from adopted executions.
CREATE TABLE IF NOT EXISTS derivation_feedback (
    id text PRIMARY KEY, -- UUID of the submitted feedback, including repeated requests.
    run text NOT NULL REFERENCES derivation_runs(id),
    selection text NOT NULL REFERENCES derivation_selections(id),
    manifest text NOT NULL, -- Exact original text, target and historical route revision.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS revision_proposals (
    id text PRIMARY KEY, -- Content address of the complete proposal and input provenance.
    feedback text NOT NULL UNIQUE REFERENCES derivation_feedback(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE item text; -- Each relation keeps historical submissions immutable.
BEGIN
    FOREACH item IN ARRAY ARRAY['derivation_feedback','revision_proposals']
    LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()',item);
        END IF;
    END LOOP;
END $$;
