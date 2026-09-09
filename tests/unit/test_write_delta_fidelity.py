"""G9 follow-up (D82): the metric that measures OUR arithmetic, split out
from the one that measures the retailer's pricing.

`CostDeltaAccuracy` was defined as expected-vs-actual delta and gated at
"exact". It was written before D68, on the assumption that the price the
product search returns is the price the cart charges. It is not: the cart
applies a per-product loyalty discount (D76), so the two disagree on 18 of
33 receipts and the gate can never be met by any correct implementation.

Left as it was, it is a permanently red gate that measures Silpo's
discount policy. Worse, the obvious "fix" -- deriving `expected_delta`
from `actual_delta` -- would delete the only signal that would catch a
genuine prediction bug.

So the question splits in two:

* `write_delta_fidelity` -- does the delta we RECORD equal the cart's own
  before/after difference? That is entirely our arithmetic, it is gated at
  1.00 absolute, and it was 7/7 across all three bundles when measured.
* `SearchPriceFidelity` -- expected versus actual, unchanged in
  computation and reported WITHOUT a gate, as the observation of D68/D76
  that it actually is.

The number 0.455 is not deleted by this split, only relabelled. These
tests exist so the split cannot quietly become the bad fix: a receipt
whose recorded delta disagrees with its own cart movement must fail.
"""

from decimal import Decimal

from src.lantern.domain.metrics import WriteDeltaRow, write_delta_fidelity


def test_a_recorded_delta_matching_the_cart_movement_passes() -> None:
    rows = [
        WriteDeltaRow(actual_delta=Decimal("161.08"), cart_delta=Decimal("161.08")),
        WriteDeltaRow(actual_delta=Decimal("14.39"), cart_delta=Decimal("14.39")),
    ]

    result = write_delta_fidelity(rows)

    assert result.value == 1.0
    assert result.n == 2


def test_the_discount_does_not_enter_this_metric() -> None:
    """The search said 178.98 and the cart charged 161.08. That gap is
    D68's, not ours -- this metric must not see it at all."""
    rows = [WriteDeltaRow(actual_delta=Decimal("161.08"), cart_delta=Decimal("161.08"))]

    assert write_delta_fidelity(rows).value == 1.0


def test_a_delta_that_disagrees_with_the_cart_fails() -> None:
    """The defect this metric exists for: a receipt claiming a movement
    the cart itself does not show."""
    rows = [
        WriteDeltaRow(actual_delta=Decimal("161.08"), cart_delta=Decimal("161.08")),
        WriteDeltaRow(actual_delta=Decimal("50.00"), cart_delta=Decimal("42.98")),
    ]

    assert write_delta_fidelity(rows).value == 0.5


def test_trailing_zeros_are_not_a_defect() -> None:
    rows = [WriteDeltaRow(actual_delta=Decimal("14.30"), cart_delta=Decimal("14.3"))]

    assert write_delta_fidelity(rows).value == 1.0


def test_a_receipt_with_no_recorded_delta_is_excluded_not_counted_wrong() -> None:
    """An unverified write records no delta. Counting it as a mismatch
    would turn an honest 'we do not know' into a manufactured defect."""
    rows = [
        WriteDeltaRow(actual_delta=None, cart_delta=Decimal("10.00")),
        WriteDeltaRow(actual_delta=Decimal("10.00"), cart_delta=Decimal("10.00")),
    ]

    result = write_delta_fidelity(rows)

    assert result.n == 1
    assert result.value == 1.0


def test_an_empty_population_is_na_not_a_clean_pass() -> None:
    result = write_delta_fidelity([])

    assert result.value is None
    assert result.n == 0
