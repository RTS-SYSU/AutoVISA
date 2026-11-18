-- Decisions and adoptions retain the exact reviewed plan and never edit prior executions.
CREATE TABLE IF NOT EXISTS proposal_decisions (
    id text PRIMARY KEY, -- Content address of actor, choice, reason and exact preview.
    proposal text NOT NULL REFERENCES revision_proposals(id),
    parent text REFERENCES proposal_decisions(id), -- Previous decision, including a rejection.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS proposal_adoptions (
    id text PRIMARY KEY, -- Client request identity makes retries return the same linked run.
    proposal text NOT NULL REFERENCES revision_proposals(id),
    decision text REFERENCES proposal_decisions(id),
    parent_run text NOT NULL REFERENCES derivation_runs(id),
    run text NOT NULL UNIQUE REFERENCES derivation_runs(id),
    manifest text NOT NULL, -- Fixed proposal, plan, decision, author and per-run budget.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS proposal_decisions_proposal ON proposal_decisions(proposal,created_at);
CREATE INDEX IF NOT EXISTS proposal_adoptions_parent ON proposal_adoptions(parent_run);
DO $$
DECLARE item text; -- Append-only relations share the existing evidence-history policy.
BEGIN
    FOREACH item IN ARRAY ARRAY['proposal_decisions','proposal_adoptions']
    LOOP
        IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='immutable') THEN
            EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION reject_edit()',item);
        END IF;
    END LOOP;
END $$;
