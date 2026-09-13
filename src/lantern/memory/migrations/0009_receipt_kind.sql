-- distinguishes an ordinary add-path receipt from a
-- compensation receipt. Without this, `CostDeltaAccuracy` (the metric
-- measuring expected-vs-actual delta) cannot exclude
-- compensation rows -- their `expected_delta` is derived from the same
-- figure as their `actual_delta` (the price the cart itself applied), so
-- each such row is a guaranteed-zero-error sample that would dilute the
-- very discrepancy the metric exists to measure.
ALTER TABLE receipts ADD COLUMN kind TEXT NOT NULL DEFAULT 'add';
