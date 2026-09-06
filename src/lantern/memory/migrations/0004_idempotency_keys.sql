-- Plan section 11: "Унікальний ключ логічної дії: власник + cart_id +
-- action_id; canonical args hash зберігається окремо... Стани журналу:
-- prepared, in_flight, confirmed, failed, unknown." The same key with
-- different arguments is rejected at the application layer (G5+G6); this
-- table only owns the storage shape and the states/unique constraint.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    id BIGSERIAL PRIMARY KEY,
    owner TEXT NOT NULL,
    cart_id TEXT NOT NULL,
    action_id UUID NOT NULL,
    canonical_args_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('prepared', 'in_flight', 'confirmed', 'failed', 'unknown')
    ),
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner, cart_id, action_id)
);
