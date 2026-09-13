"""the results chart's interval maths, pinned.

The chart is the one artefact a reader takes the stage's numbers from, and
its whole point is that four metrics sitting exactly on 1.00 or 0.00 must
NOT be drawn as certainties. A silently wrong interval would look
perfectly plausible -- a bar with a whisker on it -- so the boundary
behaviour is asserted rather than eyeballed.

Reference values recomputed independently against the exact
Clopper-Pearson interval for the same data (agreeing to within 0.002 at
these n), and recorded in the review notes's own comparison table.
"""

from scripts.render_metrics_chart import wilson


def test_a_perfect_proportion_does_not_collapse_to_a_point() -> None:
    """The defect this exists to prevent: the normal approximation gives
    [1.0, 1.0] here, claiming 33 observations settled the question."""
    low, high = wilson(1.0, 33)

    assert high == 1.0
    assert 0.89 < low < 0.90, f"expected a lower bound near 0.896, got {low}"


def test_a_zero_proportion_has_a_real_upper_bound() -> None:
    low, high = wilson(0.0, 33)

    assert low == 0.0
    assert 0.10 < high < 0.11, f"expected an upper bound near 0.104, got {high}"


def test_the_smaller_population_gives_the_wider_interval() -> None:
    """RecoveryCompletionRate is measured over 18 episodes, the rest over
    33 claims -- and must be drawn as the less certain of the two."""
    assert wilson(1.0, 18)[0] < wilson(1.0, 33)[0]


def test_mid_range_agrees_with_the_textbook_interval() -> None:
    """Away from the boundary Wilson and the normal approximation agree;
    if they did not, the implementation would be wrong rather than
    merely different."""
    import math

    p, n = 15 / 33, 33
    low, high = wilson(p, n)
    half = 1.96 * math.sqrt(p * (1 - p) / n)

    assert abs(low - (p - half)) < 0.02
    assert abs(high - (p + half)) < 0.02


def test_an_empty_population_is_not_an_interval() -> None:
    assert wilson(0.0, 0) == (0.0, 0.0)
