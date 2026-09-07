-- Per-guest OAuth tokens, one row per recovery session.
--
-- Replaces the single-file `DiskTokenStorage` for anything guest-facing:
-- that file holds ONE token, so a second guest authorising would
-- overwrite the first and both would then read the same cart. A token
-- belongs to the guest who authorised it, so it is keyed by their own
-- session.
--
-- Storage form: plain JSONB. Neon encrypts at rest and every connection
-- is TLS, and plan section 1.2's requirement is "tokens only on the
-- backend" -- which this satisfies (the browser never receives one).
-- Deliberately NOT additionally encrypted at the application layer: that
-- needs a managed key whose loss silently bricks every live session, and
-- the threat it would answer (an attacker who already has authenticated
-- read access to this database) also has the consent and receipt rows
-- next to it. Recorded as a decision rather than left implicit, because
-- "a guest's access token sits in a column" is a fact a reviewer should
-- meet in the schema, not discover.
--
-- ON DELETE CASCADE: a deleted session must not leave a live credential
-- behind it.
CREATE TABLE IF NOT EXISTS oauth_tokens (
    session_id UUID PRIMARY KEY REFERENCES sessions (session_id) ON DELETE CASCADE,
    token JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
