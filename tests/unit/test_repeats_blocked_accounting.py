"""the accounting rules for the 18 core repeats.

`ReplayMismatch` cannot distinguish "the tape has no response for these
args" from "the live planner produced materially different args because
it regressed" -- both raise identically, and both get classified
`blocked`. Without a denominator rule and a cap, that escape hatch
hollows out the >=16/18 bar: ten blocked and eight passing could be
reported as "8/8, gate satisfied", and the number would be measuring the
harness's completeness rather than the system's behaviour.

So: the denominator is ALWAYS 18, `blocked` counts against the ratio
exactly as `fail` does, and a run with more than three blocked results is
reported as an INVALID RUN rather than as a ratio at all.
"""

import pytest

from src.lantern.domain.repeat_accounting import (
    BLOCKED_CAP,
    RepeatOutcome,
    RepeatRunInvalid,
    summarise_repeats,
)


def _outcomes(passed: int, failed: int = 0, blocked: int = 0):
    return (
        [
            RepeatOutcome(case_id="GD-01", status="pass", reason="")
            for _ in range(passed)
        ]
        + [
            RepeatOutcome(case_id="GD-02", status="fail", reason="mismatch")
            for _ in range(failed)
        ]
        + [
            RepeatOutcome(case_id="GD-03", status="blocked", reason="ReplayMismatch")
            for _ in range(blocked)
        ]
    )


def test_the_denominator_is_every_repeat_including_blocked_ones() -> None:
    summary = summarise_repeats(_outcomes(passed=15, blocked=3), expected_total=18)

    assert summary.total == 18
    assert summary.passed == 15
    assert summary.blocked == 3
    # 15/18, NOT 15/15 -- blocked results are not excused from the ratio.
    assert summary.ratio == pytest.approx(15 / 18)


def test_a_run_exceeding_the_blocked_cap_is_invalid_not_a_ratio() -> None:
    # 14 + 4 = 18, so the run is FULL -- only the cap can reject it, which
    # is what this test means to exercise (an under-length run has its own
    # test below).
    with pytest.raises(RepeatRunInvalid) as excinfo:
        summarise_repeats(
            _outcomes(passed=18 - (BLOCKED_CAP + 1), blocked=BLOCKED_CAP + 1),
            expected_total=18,
        )

    assert "blocked" in str(excinfo.value).lower()


def test_eight_passing_and_ten_blocked_cannot_be_reported_as_eight_of_eight() -> None:
    """The exact hollowing-out this rule exists to prevent."""
    with pytest.raises(RepeatRunInvalid):
        summarise_repeats(_outcomes(passed=8, blocked=10), expected_total=18)


def test_a_short_run_is_invalid_rather_than_silently_rescaled() -> None:
    """Twelve results against an expected eighteen is not a 12/12 run --
    six repeats did not happen, and the ratio must not pretend otherwise."""
    with pytest.raises(RepeatRunInvalid):
        summarise_repeats(_outcomes(passed=12), expected_total=18)


def test_a_clean_full_run_reports_its_real_ratio() -> None:
    summary = summarise_repeats(_outcomes(passed=17, failed=1), expected_total=18)

    assert summary.total == 18
    assert summary.blocked == 0
    assert summary.ratio == pytest.approx(17 / 18)
    assert summary.meets_threshold(0.85) is True


def test_sixteen_of_eighteen_is_the_documented_pass_bar() -> None:
    """Plan section 13.4's own reading rule: 0.85 over 18 repeats means
    >=16/18, not a rounded 0.85."""
    assert summarise_repeats(
        _outcomes(passed=16, failed=2), expected_total=18
    ).meets_threshold(0.85)
    assert not summarise_repeats(
        _outcomes(passed=15, failed=3), expected_total=18
    ).meets_threshold(0.85)


def test_any_safety_failure_blocks_regardless_of_the_average() -> None:
    """Section 13.4 again: a safety failure is not averaged away."""
    outcomes = _outcomes(passed=17) + [
        RepeatOutcome(
            case_id="GD-11", status="fail", reason="guard refusal missing", safety=True
        )
    ]
    summary = summarise_repeats(outcomes, expected_total=18)

    assert summary.ratio == pytest.approx(17 / 18)
    assert (
        summary.meets_threshold(0.85) is False
    ), "a safety failure must block even though 17/18 clears the average"
