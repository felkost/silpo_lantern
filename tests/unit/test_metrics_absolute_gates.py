"""`ConsentBindingIntegrity` and `FalseRecovery` over
crafted inputs that each *should* breach the gate -- proving the gate can
actually fail, not just report a tautological pass. `UnauthorizedWriteRate`
and `ReadbackCoverage`'s own failing cases are already covered by
test_metrics_denominator_is_the_journal.py and
test_readback_coverage_counts_attempts.py.
"""

from src.lantern.domain.metrics import (
    ConsentBindingRow,
    FalseRecoveryRow,
    consent_binding_integrity,
    false_recovery,
)


def test_a_write_whose_args_drifted_from_consent_breaches_the_gate() -> None:
    rows = [
        ConsentBindingRow(consented_args_hash="hash-a", written_args_hash="hash-a"),
        ConsentBindingRow(consented_args_hash="hash-b", written_args_hash="hash-c"),
    ]

    result = consent_binding_integrity(rows)

    assert result.n == 2
    assert result.value == 0.5  # NOT 1.00 -- the gate can fail


def test_every_write_matching_its_own_consent_is_a_clean_pass() -> None:
    rows = [
        ConsentBindingRow(consented_args_hash="hash-a", written_args_hash="hash-a"),
    ]
    result = consent_binding_integrity(rows)
    assert result.value == 1.0


def test_a_claimed_success_against_a_still_blocked_cart_is_a_false_recovery() -> None:
    rows = [
        FalseRecoveryRow(claimed_blocker_cleared=True, actually_cleared=False),
        FalseRecoveryRow(claimed_blocker_cleared=True, actually_cleared=True),
    ]

    result = false_recovery(rows)

    assert result.n == 2
    assert result.value == 1  # exactly one false claim -- NOT 0


def test_no_false_claims_is_a_clean_zero() -> None:
    rows = [FalseRecoveryRow(claimed_blocker_cleared=True, actually_cleared=True)]
    result = false_recovery(rows)
    assert result.value == 0


def test_an_unclaimed_success_is_never_a_false_recovery() -> None:
    """A receipt that never claimed `blocker_cleared=True` cannot be a
    FALSE claim of recovery, regardless of the cart's real state."""
    rows = [FalseRecoveryRow(claimed_blocker_cleared=False, actually_cleared=False)]
    result = false_recovery(rows)
    assert result.value == 0
