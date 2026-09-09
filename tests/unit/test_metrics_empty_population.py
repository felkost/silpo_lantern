"""T16 (G9 spec): `RecoveryCompletionRate` with `n == 0` returns N/A, never
0% -- plan section 13.1's own rule, because a 0% completion rate over zero
episodes reads as "every guest failed" when in fact none were measured.
`DisclosureRate` never counts "unknown" (visibility not verified) as
"hidden" -- an unmeasured constraint is not evidence it was invisible to
the guest.
"""

from src.lantern.domain.metrics import (
    DisclosureRow,
    RecoveryEpisode,
    disclosure_rate,
    recovery_completion_rate,
)


def test_zero_episodes_is_not_applicable_never_zero_percent() -> None:
    result = recovery_completion_rate([])
    assert result.n == 0
    assert result.value is None


def test_completion_rate_is_a_plain_fraction_when_episodes_exist() -> None:
    episodes = [
        RecoveryEpisode(completed=True),
        RecoveryEpisode(completed=True),
        RecoveryEpisode(completed=False),
    ]
    result = recovery_completion_rate(episodes)
    assert result.n == 3
    assert result.value == 2 / 3


def test_unknown_visibility_is_excluded_not_counted_as_hidden() -> None:
    rows = [
        DisclosureRow(had_invisible_constraint=True, visibility_verified=True),
        DisclosureRow(had_invisible_constraint=None, visibility_verified=False),
    ]

    result = disclosure_rate(rows)

    # denominator is sessions with VERIFIED visibility only -- the second
    # row (unverified) must not silently count toward either side.
    assert result.n == 1
    assert result.value == 1.0


def test_a_verified_session_with_no_invisible_constraint_lowers_the_rate() -> None:
    rows = [
        DisclosureRow(had_invisible_constraint=True, visibility_verified=True),
        DisclosureRow(had_invisible_constraint=False, visibility_verified=True),
    ]
    result = disclosure_rate(rows)
    assert result.n == 2
    assert result.value == 0.5


def test_no_verified_sessions_is_not_applicable() -> None:
    rows = [DisclosureRow(had_invisible_constraint=None, visibility_verified=False)]
    result = disclosure_rate(rows)
    assert result.n == 0
    assert result.value is None
