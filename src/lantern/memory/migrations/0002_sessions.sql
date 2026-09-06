-- Plan section 21.2. One row per guest recovery session; links to the
-- LangGraph checkpointer's own thread_id so a session can resume from a
-- fresh process after an interrupt (plan section 11).
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    thread_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
