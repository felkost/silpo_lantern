-- an earlier decision (the initial review): the consent record the brief
-- describes carries cart_id, prompt_version and policy_version, and none
-- of the three existed on `consents` — a consent could not be bound to
-- the cart it was granted against by id, nor to the prompt/policy version
-- that produced it. Added here rather than inferred from other columns,
-- because `state_hash` intentionally excludes cart_id (it hashes the
-- cart's own contents, not its identity) and the idempotency key's own
-- unique constraint (`owner, cart_id, action_id`) needs a `cart_id` to
-- join against.
ALTER TABLE consents ADD COLUMN cart_id TEXT NOT NULL DEFAULT '';
ALTER TABLE consents ALTER COLUMN cart_id DROP DEFAULT;
ALTER TABLE consents ADD COLUMN prompt_version TEXT;
ALTER TABLE consents ADD COLUMN policy_version TEXT;

-- The receipt as `0005` defined it cannot represent what the brief
-- requires the metrics to measure: `ReadbackCoverage` needs "attempt made" and
-- "verification succeeded" as separate facts, `CostDeltaAccuracy` needs a
-- stored expected delta to compare against, and no column let a receipt
-- be joined back to its own LangSmith trace. `verified` stays (existing
-- callers/tests read it) and is derived from `status` going forward.
ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'unverified'
    CHECK (status IN ('receipt', 'unverified'));
ALTER TABLE receipts ALTER COLUMN status DROP DEFAULT;
ALTER TABLE receipts ADD COLUMN reason TEXT NOT NULL DEFAULT '';
ALTER TABLE receipts ALTER COLUMN reason DROP DEFAULT;
ALTER TABLE receipts ADD COLUMN expected_delta NUMERIC;
ALTER TABLE receipts ADD COLUMN actual_delta NUMERIC;
ALTER TABLE receipts ADD COLUMN trace_id TEXT;
