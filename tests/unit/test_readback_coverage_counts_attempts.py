"""T13 (G9 spec): `ReadbackCoverage` must not be implemented as
"verification succeeded" -- a claim whose read-back was unreachable still
counts as covered (an attempt was made), and its receipt correctly reads
`unverified`, never a fabricated success (DR-12).
"""

from src.lantern.domain.metrics import JournalClaim, readback_coverage


class _FakeReceipt:
    def __init__(self, action_id: str, status: str) -> None:
        self.action_id = action_id
        self.status = status


def test_a_claim_whose_readback_was_unreachable_still_counts_as_covered() -> None:
    claims = [
        JournalClaim(owner="o", cart_id="c", action_id="a1", state="confirmed"),
    ]
    receipts_by_action_id = {"a1": _FakeReceipt("a1", status="unverified")}

    result = readback_coverage(claims, receipts_by_action_id)

    assert result.n == 1
    assert result.value == 1.0  # attempt made, coverage is about the attempt


def test_a_claim_with_no_receipt_at_all_is_not_covered() -> None:
    """Only a genuine crash-before-persist leaves no receipt -- that IS a
    coverage gap, distinct from an unreachable read-back (which still
    produces an `unverified` receipt)."""
    claims = [
        JournalClaim(owner="o", cart_id="c", action_id="crashed", state="in_flight"),
    ]
    result = readback_coverage(claims, {})

    assert result.n == 1
    assert result.value == 0.0


def test_zero_claims_is_not_applicable() -> None:
    result = readback_coverage([], {})
    assert result.n == 0
    assert result.value is None
