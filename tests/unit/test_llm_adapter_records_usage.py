"""T25 (G9 spec): tokens and cost for a live run come from the provider's
own reported `usage`, never from an estimate.

D59 established that this project has NO other source: `enforce_budget`
is called from nowhere and `cycles_used`/`tokens_used` are never
incremented, so plan section 13.4's per-run "tokens and cost" would
otherwise have nothing behind it at all.

The arithmetic is pure and lives in `domain/repeat_accounting.py`; the
extraction from a live response lives in `scripts/core_e2e_repeats.py`,
which is the only consumer. This file pins both: the cost formula against
the pinned price table, and the rule that a response carrying no usage
block records zeros rather than a guess.
"""

import pytest

from src.lantern.domain.repeat_accounting import TokenUsage, cost_usd, total_cost_usd
from scripts.core_e2e_repeats import usage_from_response


class _FakeMessage:
    def __init__(self, usage_metadata=None) -> None:
        self.usage_metadata = usage_metadata


def test_cost_is_computed_from_measured_tokens_and_the_pinned_price() -> None:
    # google/gemini-3.5-flash-lite in config/models.yaml: 0.30 in, 2.50 out.
    usage = TokenUsage(input_tokens=6000, output_tokens=1200)

    cost = cost_usd(usage, input_usd_per_million=0.30, output_usd_per_million=2.50)

    assert cost == pytest.approx((6000 * 0.30 + 1200 * 2.50) / 1_000_000)


def test_zero_tokens_cost_nothing() -> None:
    assert (
        cost_usd(
            TokenUsage(0, 0), input_usd_per_million=1.0, output_usd_per_million=1.0
        )
        == 0.0
    )


def test_total_cost_sums_every_call() -> None:
    assert total_cost_usd([0.001, 0.002, 0.0005]) == pytest.approx(0.0035)


def test_usage_is_read_from_the_providers_own_report() -> None:
    message = _FakeMessage(usage_metadata={"input_tokens": 1234, "output_tokens": 56})

    usage = usage_from_response(message)

    assert usage.input_tokens == 1234
    assert usage.output_tokens == 56


def test_a_response_with_no_usage_block_records_zeros_not_a_guess() -> None:
    """An unmeasured call must be visibly unmeasured. Estimating tokens
    from prompt length here would put an invented number into a cost
    report that the $20 project ceiling is judged against."""
    usage = usage_from_response(_FakeMessage(usage_metadata=None))

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


def test_a_response_that_is_not_a_message_at_all_records_zeros() -> None:
    usage = usage_from_response(object())
    assert usage == TokenUsage(0, 0)
