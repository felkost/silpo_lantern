-- CLAUDE.md invariant: "Consent is bound to a specific action, not a
-- session" — action_id, canonical args, args_hash, state_hash, and expiry
-- (plan section 11: TTL initially 5 min). Exact consumption/expiry logic is
-- G5+G6's job; this stage only owns the table existing.
CREATE TABLE IF NOT EXISTS consents (
    action_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions (session_id),
    owner TEXT NOT NULL,
    canonical_args JSONB NOT NULL,
    args_hash TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
