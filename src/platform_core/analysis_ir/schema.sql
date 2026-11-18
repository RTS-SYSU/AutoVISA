-- Mapping receipts are separate from proof outcomes and never advance a frozen review.
CREATE TABLE IF NOT EXISTS formal_mappings (
    id text PRIMARY KEY, -- Content address of the translation receipt.
    freeze_id text NOT NULL REFERENCES review_freezes(id),
    status text NOT NULL CHECK (status IN ('mapped','partial','blocked','failed')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='formal_mappings'::regclass AND tgname='immutable') THEN
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON formal_mappings
        FOR EACH STATEMENT EXECUTE FUNCTION reject_edit();
    END IF;
END $$;
