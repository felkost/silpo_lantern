-- Plan section 6.1 step 10: "Receipt: «було→стало», фактичні суми,
-- усунені/нові блокери, checkoutWebLink." `verified` records whether the
-- mandatory read-back after a write actually succeeded (CLAUDE.md
-- invariant: an unreachable read-back produces `unverified`, never a
-- successful receipt — DR-12).
CREATE TABLE IF NOT EXISTS receipts (
    action_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions (session_id),
    owner TEXT NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    verified BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
