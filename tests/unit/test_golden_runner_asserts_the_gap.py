"""the runner needs a money assertion, or a discount case can
say nothing about discounts.

GD-05's whole subject is that `minOrderCost` is compared against
`productsTotal` alone -- never `total` or `totalAfterDiscounts`
(`CLAUDE.md`'s own invariant, a previously-shipped mistake the field
report reversed). On a discounted cart those three numbers differ by more
than the gap itself, so a case that asserts only `primary_code` passes
just as happily against an implementation comparing the wrong one.

`gap` is compared as a STRING of the `Decimal`, not as a float: `4.60`
and `4.6` are the same `Decimal` and the same money, and a golden file
must not fail on trailing-zero formatting.
"""

from decimal import Decimal

import pytest

from src.lantern.domain.models import Diagnosis
from tests.golden.test_golden_cases import _assert_expected_outcome


def _state(gap: object) -> dict:
    diagnosis = Diagnosis.model_construct(
        primary_code="order.cost.min", blockers=[], gap=gap, gap_is_borderline=False
    )
    return {"status": "awaiting_consent", "diagnosis": diagnosis}


def test_a_matching_gap_passes() -> None:
    _assert_expected_outcome("GD-X", {"gap": "175.68"}, _state(Decimal("175.68")))


def test_trailing_zeros_do_not_decide_the_result() -> None:
    _assert_expected_outcome("GD-X", {"gap": "4.60"}, _state(Decimal("4.6")))


def test_a_wrong_gap_fails() -> None:
    with pytest.raises(AssertionError, match="gap"):
        _assert_expected_outcome("GD-X", {"gap": "175.68"}, _state(Decimal("121.26")))


def test_no_diagnosis_at_all_fails_rather_than_passing_vacuously() -> None:
    with pytest.raises(AssertionError, match="gap"):
        _assert_expected_outcome("GD-X", {"gap": "175.68"}, {"status": "aborted"})
