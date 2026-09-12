"""`CostDeltaAccuracy` excludes `kind="compensate"` receipts
-- their `expected_delta` is derived from the same figure as their
`actual_delta` (`domain/compensation.py`'s own derivation), so every such
row is a guaranteed-zero-error sample that would dilute the very
discrepancy the metric exists to measure -- and excludes rows with
`actual_delta IS NULL` (no write attempted, or unverified with no delta
recorded).
"""

from decimal import Decimal

from src.lantern.domain.metrics import CostDeltaRow, cost_delta_accuracy


def test_compensation_receipts_are_excluded_from_the_denominator() -> None:
    rows = [
        CostDeltaRow(
            kind="add", expected_delta=Decimal("100.00"), actual_delta=Decimal("90.00")
        ),
        CostDeltaRow(
            kind="compensate",
            expected_delta=Decimal("-90.00"),
            actual_delta=Decimal("-90.00"),
        ),
    ]

    result = cost_delta_accuracy(rows)

    assert result.n == 1  # the compensation row never enters the denominator
    assert result.value == 0.0  # the one remaining row is a mismatch


def test_rows_with_no_actual_delta_are_excluded() -> None:
    rows = [
        CostDeltaRow(kind="add", expected_delta=Decimal("50.00"), actual_delta=None),
        CostDeltaRow(
            kind="add", expected_delta=Decimal("50.00"), actual_delta=Decimal("50.00")
        ),
    ]

    result = cost_delta_accuracy(rows)

    assert result.n == 1
    assert result.value == 1.0


def test_an_exact_match_scores_one_and_a_mismatch_scores_zero() -> None:
    rows = [
        CostDeltaRow(
            kind="add", expected_delta=Decimal("10.00"), actual_delta=Decimal("10.00")
        ),
        CostDeltaRow(
            kind="add", expected_delta=Decimal("10.00"), actual_delta=Decimal("10.01")
        ),
    ]

    result = cost_delta_accuracy(rows)

    assert result.n == 2
    assert result.value == 0.5


def test_no_eligible_rows_is_not_applicable() -> None:
    rows = [
        CostDeltaRow(kind="compensate", expected_delta=Decimal("1"), actual_delta=None)
    ]
    result = cost_delta_accuracy(rows)
    assert result.n == 0
    assert result.value is None
