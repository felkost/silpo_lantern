"""The actual attack scenario is a
well-formed value that is wrong, not an absent field — "foreign cart_id,
invented productId, false sum, у валідному JSON". A gate
that only checks field *presence* would let a negative price, a zero price,
or `available: False` straight through, since all three are present,
correctly-typed values. This module checks type AND range, not presence
alone.
"""

from datetime import datetime, timezone

from src.lantern.domain.evidence_gate import RawCandidate, gate_candidates


def _candidate(**overrides: object) -> RawCandidate:
    defaults: dict = {
        "call_id": "call-1",
        "source_tool": "silpo_find_products_batch",
        "external_product_id": 12345,
        "slug": "some-product",
        "name": "Some Product",
        "price_raw": 39.99,
        "available_raw": True,
        "captured_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return RawCandidate(**defaults)  # type: ignore[arg-type]


def test_a_well_formed_negative_price_is_rejected() -> None:
    assert gate_candidates([_candidate(price_raw=-10.0)]) == []


def test_a_well_formed_zero_price_is_rejected() -> None:
    assert gate_candidates([_candidate(price_raw=0)]) == []


def test_available_false_is_rejected_even_with_a_valid_price() -> None:
    assert gate_candidates([_candidate(available_raw=False)]) == []


def test_a_truthy_non_boolean_availability_is_not_accepted_as_true() -> None:
    """`available_raw is True` is an identity check on purpose — a stray
    `1` or `"true"` from a malformed upstream response must not pass
    through Python's own truthiness as if it were a real boolean `True`.
    """
    assert gate_candidates([_candidate(available_raw=1)]) == []
    assert gate_candidates([_candidate(available_raw="true")]) == []


def test_a_non_numeric_price_string_is_rejected_not_crashed_on() -> None:
    assert gate_candidates([_candidate(price_raw="call support")]) == []


def test_a_genuinely_valid_candidate_still_survives() -> None:
    """Sanity check alongside the rejection cases above — a gate that
    rejects everything is trivially "safe" and useless; this confirms the
    happy path still works after all the range checks are in place."""
    survivors = gate_candidates([_candidate()])
    assert len(survivors) == 1
    assert survivors[0].availability is True
