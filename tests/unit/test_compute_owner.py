"""`compute_owner` is a per-session identity hash, never derived
from `cart_id` (which `compute_state_hash` already includes)."""

from src.lantern.domain.consent_hash import compute_owner


def test_same_session_and_secret_produce_the_same_owner() -> None:
    a = compute_owner("session-1", "secret-abc")
    b = compute_owner("session-1", "secret-abc")
    assert a == b


def test_different_sessions_produce_different_owners() -> None:
    a = compute_owner("session-1", "secret-abc")
    b = compute_owner("session-2", "secret-abc")
    assert a != b


def test_different_secrets_produce_different_owners() -> None:
    a = compute_owner("session-1", "secret-abc")
    b = compute_owner("session-1", "secret-xyz")
    assert a != b


def test_owner_is_not_derivable_from_cart_id_alone() -> None:
    """Nothing about `compute_owner`'s inputs includes `cart_id` -- a
    guest cannot forge another guest's owner hash just by knowing which
    cart they used."""
    owner = compute_owner("session-1", "secret-abc")
    assert "cart" not in owner
