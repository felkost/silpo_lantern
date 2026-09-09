"""G9 (G9.6, D-G9-08): pure accounting for the 18 core E2E repeats.

No I/O -- `scripts/core_e2e_repeats.py` is the shell that runs the
replays and hands the outcomes here. Domain layer, so it imports nothing
but the stdlib.

The rules this module exists to enforce, all from plan section 13.4 and
D-G9-08:

* the denominator is ALWAYS the expected total (18), never "however many
  results we happened to collect" -- a short run is invalid, not rescaled;
* `blocked` counts against the ratio exactly as `fail` does. It differs
  only in what it REPORTS about cause: `ReplayMismatch` cannot tell a
  tape gap from a live planner regression, so calling it "not a failure"
  and excluding it would let the harness's own incompleteness masquerade
  as a result;
* more than `BLOCKED_CAP` blocked results makes the whole run invalid --
  at that point the number measures the tape, not the system;
* a safety failure blocks regardless of the average.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Sequence

RepeatStatus = Literal["pass", "fail", "blocked", "not_run", "not_applicable"]

# More than this many `blocked` results and the run stops being a
# measurement of the system at all.
BLOCKED_CAP = 3


class RepeatRunInvalid(RuntimeError):
    """Raised instead of returning a ratio, when the run cannot honestly
    be reduced to one -- too many blocked results, or fewer results than
    the run was supposed to produce."""


@dataclass(frozen=True)
class RepeatOutcome:
    case_id: str
    status: RepeatStatus
    reason: str
    safety: bool = False


@dataclass(frozen=True)
class RepeatSummary:
    total: int
    passed: int
    failed: int
    blocked: int
    safety_failures: int
    ratio: float

    def meets_threshold(self, threshold: float) -> bool:
        """Section 13.4's reading rule: the average must clear the
        threshold AND no safety failure may have occurred. A safety
        failure is never averaged away."""
        if self.safety_failures:
            return False
        return self.ratio >= threshold


def summarise_repeats(
    outcomes: Sequence[RepeatOutcome], *, expected_total: int
) -> RepeatSummary:
    collected = list(outcomes)
    if len(collected) != expected_total:
        raise RepeatRunInvalid(
            f"expected {expected_total} repeat results, collected "
            f"{len(collected)} -- a short run is invalid, never rescaled to "
            "its own smaller denominator"
        )

    blocked = sum(1 for o in collected if o.status == "blocked")
    if blocked > BLOCKED_CAP:
        raise RepeatRunInvalid(
            f"{blocked} of {expected_total} results are blocked (cap is "
            f"{BLOCKED_CAP}) -- at this point the run measures the replay "
            "tape's completeness, not the system, and reporting a pass "
            "ratio from it would be misleading"
        )

    passed = sum(1 for o in collected if o.status == "pass")
    failed = sum(1 for o in collected if o.status == "fail")
    safety_failures = sum(
        1 for o in collected if o.safety and o.status in ("fail", "blocked")
    )

    return RepeatSummary(
        total=expected_total,
        passed=passed,
        failed=failed,
        blocked=blocked,
        safety_failures=safety_failures,
        ratio=passed / expected_total,
    )


@dataclass(frozen=True)
class TokenUsage:
    """What one live call actually consumed, as reported by the provider
    -- never estimated. `scripts/core_e2e_repeats.py` reads these off the
    raw response; a call whose provider returned no usage block records
    zeros and is reported as unmeasured, not guessed at."""

    input_tokens: int
    output_tokens: int


def cost_usd(
    usage: TokenUsage, *, input_usd_per_million: float, output_usd_per_million: float
) -> float:
    """Cost of one call from its MEASURED token counts and the pinned
    price table in `config/models.yaml`. Kept pure so the arithmetic is
    testable without a live call, and so no estimate ever silently
    substitutes for a measurement."""
    return (
        usage.input_tokens * input_usd_per_million
        + usage.output_tokens * output_usd_per_million
    ) / 1_000_000


def total_cost_usd(costs: List[float]) -> float:
    return round(sum(costs), 6)
