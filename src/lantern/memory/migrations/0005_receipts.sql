-- A receipt records before/after state, actual sums, resolved/new blockers,
-- and the checkout web link. `verified` records whether the mandatory
-- read-back after a write actually succeeded: an unreachable read-back
-- produces `unverified`, never a successful receipt.
CREATE TABLE IF NOT EXISTS receipts (
    action_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions (session_id),
    owner TEXT NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    verified BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
