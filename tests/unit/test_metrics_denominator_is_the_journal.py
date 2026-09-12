"""`UnauthorizedWriteRate` and `ReadbackCoverage` are computed
over the idempotency journal (claims made), never over `receipts`.
Computed over `receipts`, both metrics are identically 0.00/1.00 for every
database state this code can reach -- a guard refusal writes no receipt
row at all, and `Receipt` cannot be constructed without `claim_and_consume`
having already won a journal claim -- so they would be gates that cannot
fail. The journal survives a crash between the write call and
`persist_receipt`; `receipts` does not.
"""

from src.lantern.domain.metrics import JournalClaim, unauthorized_write_rate


def test_a_claim_with_no_matching_consent_counts_as_unauthorized() -> None:
    claims = [
        JournalClaim(owner="o1", cart_id="c1", action_id="a1", state="confirmed"),
        JournalClaim(owner="o1", cart_id="c1", action_id="a2", state="confirmed"),
    ]
    # a2 has no matching consent -- a write claimed without one, exactly
    # the shape this metric exists to catch.
    consents_by_action_id = {"a1": object()}

    result = unauthorized_write_rate(claims, consents_by_action_id)

    assert result.value == 0.5
    assert result.n == 2


def test_the_denominator_is_every_claim_not_every_receipt() -> None:
    """A claim that crashed between the write call and `persist_receipt`
    has no receipt at all -- the journal still counts it. Simulated here
    by a claim whose action_id has a valid consent (so it is NOT
    unauthorized) but which would be invisible to a receipts-based
    computation entirely."""
    claims = [
        JournalClaim(owner="o1", cart_id="c1", action_id="crashed", state="in_flight"),
    ]
    consents_by_action_id = {"crashed": object()}

    result = unauthorized_write_rate(claims, consents_by_action_id)

    assert result.n == 1  # counted, even though no receipt exists for it
    assert result.value == 0.0


def test_zero_claims_is_reported_as_not_applicable_not_zero() -> None:
    result = unauthorized_write_rate([], {})
    assert result.n == 0
    assert result.value is None
