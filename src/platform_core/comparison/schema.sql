-- A comparison is a saved observation, never an edit to a run or a route selection.
CREATE TABLE IF NOT EXISTS run_comparisons (
    id text PRIMARY KEY, -- Content address of both exact versions and their observed differences.
    parent_run text NOT NULL REFERENCES derivation_runs(id),
    child_run text NOT NULL REFERENCES derivation_runs(id),
    parent_selection text NOT NULL REFERENCES derivation_selections(id),
    child_selection text NOT NULL REFERENCES derivation_selections(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS run_comparisons_child ON run_comparisons(child_run,created_at);
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='run_comparisons'::regclass AND tgname='immutable') THEN
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON run_comparisons
        FOR EACH STATEMENT EXECUTE FUNCTION reject_edit();
    END IF;
END $$;
