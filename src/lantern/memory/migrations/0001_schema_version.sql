-- An incompatible state version without a migration must fail safe. One
-- row tracks the currently-applied application schema version, distinct
-- from LangGraph's own checkpoint_migrations (owned by AsyncPostgresSaver).
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
