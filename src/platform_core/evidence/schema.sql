-- W02 ledger. The connection search path places the tables and trigger function in this schema.
CREATE SCHEMA IF NOT EXISTS autorta_w02;

-- Each row pins one context or goal revision. The latest generation is the head for its kind and name.
CREATE TABLE IF NOT EXISTS revisions (
    id text PRIMARY KEY,             -- SHA-256 of kind, name, parent, context and canonical body.
    kind text NOT NULL CHECK (kind IN ('context','goal')),
    name text NOT NULL,              -- Logical identifier retained across edits.
    generation integer NOT NULL CHECK (generation > 0),  -- Starts at one for each kind/name pair.
    parent text REFERENCES revisions(id),  -- Previous head, or NULL for the first revision.
    context text REFERENCES revisions(id), -- Frozen context for a goal; NULL on a context row.
    body jsonb NOT NULL,             -- Goal proposition or context profile, hypotheses and note.
    UNIQUE(kind,name,generation),
    CHECK ((kind = 'context') = (context IS NULL))
);
-- A fresh attempt ID records every submission, including repeated requests and interrupted checks.
CREATE TABLE IF NOT EXISTS attempts (
    id text PRIMARY KEY,
    target text NOT NULL REFERENCES revisions(id),  -- Exact goal revision submitted for checking.
    request jsonb NOT NULL,          -- Structured proof term or ordered application request.
    -- Database clock at registration, before the checker is invoked.
    started timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- An attempt with no outcome is interrupted or running, never successful.
CREATE TABLE IF NOT EXISTS outcomes (
    attempt text PRIMARY KEY REFERENCES attempts(id),
    code text NOT NULL,              -- Conditional, complete or a diagnostic code.
    detail text NOT NULL,            -- Readable result or rejection reason.
    -- Content address of the receipt manifest in the separate object directory.
    manifest text NOT NULL CHECK (manifest ~ '^[0-9a-f]{64}$'),
    -- Database clock when the outcome row is written.
    ended timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Each row connects one composed outcome to a specific previously checked input.
CREATE TABLE IF NOT EXISTS receipt_inputs (
    attempt text NOT NULL REFERENCES outcomes(attempt),
    position integer NOT NULL,       -- Zero selects the rule; subsequent slots follow premise order.
    dependency text NOT NULL REFERENCES outcomes(attempt),
    PRIMARY KEY(attempt,position)
);
-- Retrieve all attempts for an exact target revision when assessing its proof routes.
CREATE INDEX IF NOT EXISTS attempts_target ON attempts(target);
-- Reject edits to existing evidence history at statement level.
-- @raise raise_exception On every triggered UPDATE, DELETE or TRUNCATE statement.
CREATE OR REPLACE FUNCTION reject_edit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'W02 history is append-only';
END $$;
DO $$
DECLARE t text;  -- Table name whose append-only trigger is being installed.
BEGIN
    FOREACH t IN ARRAY ARRAY['revisions','attempts','outcomes','receipt_inputs'] LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=t::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I
                            FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()', t);
        END IF;
    END LOOP;
END $$;

