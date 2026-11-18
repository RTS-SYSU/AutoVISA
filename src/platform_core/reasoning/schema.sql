-- Runs and selections are append-only; proof attempts remain owned by W02.
CREATE TABLE IF NOT EXISTS derivation_runs (
    id text PRIMARY KEY, -- UUID of one actual local rule execution.
    mapping text NOT NULL REFERENCES formal_mappings(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS derivation_results (
    run text PRIMARY KEY REFERENCES derivation_runs(id),
    manifest text NOT NULL, -- Content-addressed requests, graphs, receipts and compiler inputs.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS derivation_selections (
    id text PRIMARY KEY, -- Content address of exact route choices.
    run text NOT NULL REFERENCES derivation_runs(id),
    parent text REFERENCES derivation_selections(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE item text;
BEGIN
    FOREACH item IN ARRAY ARRAY['derivation_runs','derivation_results','derivation_selections']
    LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()',item);
        END IF;
    END LOOP;
END $$;
