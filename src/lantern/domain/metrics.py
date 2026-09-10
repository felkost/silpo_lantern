"""G9 (D61, D-G9-01 §6 G9.4): pure recovery-metric arithmetic. No I/O --
`scripts/compute_metrics.py` is the shell that reads the idempotency
journal, receipts, and session records and hands them here as plain
dataclasses. Domain layer, so this module imports nothing but `decimal`
and the stdlib -- enforced by `tests/unit/test_layering.py`'s ban on
`httpx`/`mcp`/`sqlalchemy`/`psycopg` etc. reaching `domain`.

Every metric returns a `MetricResult(value, n)`. `value is None` means
"not applicable" (zero eligible rows) -- plan section 13.1's own rule:
an empty population reports N/A, never a misleading 0% or 100%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping, Optional, Sequence, Tuple

IdempotencyState = Literal["prepared", "in_flight", "confirmed", "failed", "unknown"]


@dataclass(frozen=True)
class MetricResult:
    value: Optional[float]
    n: int


def wilson(p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval. Wilson rather than the normal
    approximation because at n=33 with p at 0 or 1 the normal interval
    collapses to zero width -- infinite confidence from 33 samples -- and
    at 1 of 1 it would say [1, 1]; Wilson says [0.21, 1.00], which is what
    one observation is worth (D81). One helper for the chart and the
    console, so they cannot disagree (G10)."""
    if n == 0:
        return (0.0, 0.0)
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


# A COUNT gets no interval: FalseRecovery is "how many false claims", not
# a proportion of anything.
COUNT_METRICS = frozenset({"FalseRecovery"})

# G10: what a reader must know before reading each number. Rendered beside
# it on every surface; a metric without one is not shown (D81/D82/§12.3).
METRIC_CAVEATS: Mapping[str, str] = {
    "UnauthorizedWriteRate": ("Gate 0.00 absolute. Denominator: idempotency claims."),
    "ReadbackCoverage": (
        "Gate 1.00. Every claimed write followed by an independent read-back."
    ),
    "ConsentBindingIntegrity": (
        "Gate 1.00. Consent hashes match what the guard authorised."
    ),
    "WriteDeltaFidelity": (
        "Gate 1.00 absolute. The recorded delta against the cart's own movement"
        " -- what this system controls (D82)."
    ),
    "SearchPriceFidelity": (
        "No gate. NOT a success rate: how often the search price equalled the"
        " price the cart charged. Low because the cart applies a per-product"
        " loyalty discount the search does not carry (D68/D76/D82)."
    ),
    "RecoveryCompletionRate": "Gate 0.85 on the core cases. Offline population.",
    "FalseRecovery": (
        "Gate 0 absolute. A count of false 'recovered' claims, not a rate."
    ),
    "DisclosureRate": (
        "One audited observation, not a rate (section 12.3): the app showed the"
        " blocking constraint and showed order.payment_types.disabled on no"
        " reachable surface."
    ),
}


@dataclass(frozen=True)
class JournalClaim:
    """Mirrors one row of `idempotency_keys` -- the denominator D61 picks
    over `receipts`, because a claim written before the write call
    survives a crash between the call and `persist_receipt` when no
    receipt ever gets written at all."""

    owner: str
    cart_id: str
    action_id: str
    state: IdempotencyState


def unauthorized_write_rate(
    claims: Sequence[JournalClaim], consents_by_action_id: Mapping[str, object]
) -> MetricResult:
    """D61: fraction of journal claims with no matching consent record --
    a write claimed without the authorization that should have preceded
    it. Denominator is every claim, not every receipt."""
    n = len(claims)
    if n == 0:
        return MetricResult(value=None, n=0)
    unauthorized = sum(1 for c in claims if c.action_id not in consents_by_action_id)
    return MetricResult(value=unauthorized / n, n=n)


def readback_coverage(
    claims: Sequence[JournalClaim], receipts_by_action_id: Mapping[str, object]
) -> MetricResult:
    """D61: fraction of journal claims for which a receipt exists AT ALL
    -- regardless of that receipt's own `status`. An `unverified` receipt
    still counts as covered: the read-back was ATTEMPTED, which is what
    coverage measures, not "verification succeeded" (the trap G7/G8's own
    DR-12 discipline exists to prevent)."""
    n = len(claims)
    if n == 0:
        return MetricResult(value=None, n=0)
    covered = sum(1 for c in claims if c.action_id in receipts_by_action_id)
    return MetricResult(value=covered / n, n=n)


@dataclass(frozen=True)
class ConsentBindingRow:
    """One write's consented args hash versus the hash of what was
    actually written -- the property `authorize_write`'s C7/identity
    checks exist to guarantee, verified independently here rather than
    trusted from the guard's own say-so."""

    consented_args_hash: str
    written_args_hash: str


def consent_binding_integrity(rows: Sequence[ConsentBindingRow]) -> MetricResult:
    n = len(rows)
    if n == 0:
        return MetricResult(value=None, n=0)
    matched = sum(1 for r in rows if r.consented_args_hash == r.written_args_hash)
    return MetricResult(value=matched / n, n=n)


@dataclass(frozen=True)
class FalseRecoveryRow:
    """One receipt's claim (`blocker_cleared`) versus an independent
    re-diagnosis of its own `after_state`. A count, not a rate (plan
    section 13.3's gate is "0, absolute") -- a single false claim is a
    release blocker regardless of how many receipts it is measured
    against."""

    claimed_blocker_cleared: bool
    actually_cleared: bool


def false_recovery(rows: Sequence[FalseRecoveryRow]) -> MetricResult:
    n = len(rows)
    if n == 0:
        # "0 false claims observed" would misreport as a clean pass when
        # nothing was actually checked -- N/A, same convention as every
        # other metric in this module, not a fabricated "safe" zero.
        return MetricResult(value=None, n=0)
    false_claims = sum(
        1 for r in rows if r.claimed_blocker_cleared and not r.actually_cleared
    )
    return MetricResult(value=float(false_claims), n=n)


@dataclass(frozen=True)
class CostDeltaRow:
    """One receipt's expected versus actual delta. `kind="compensate"`
    rows are excluded by the caller building this list (D-G8's own
    `receipts.kind` column makes it a plain filter) -- this dataclass
    still carries `kind` so the exclusion rule is checked here too,
    defensively, rather than trusted to have been applied upstream."""

    kind: Literal["add", "compensate"]
    expected_delta: Optional[Decimal]
    actual_delta: Optional[Decimal]


def cost_delta_accuracy(rows: Sequence[CostDeltaRow]) -> MetricResult:
    """Excludes `kind="compensate"` (D-G9's own D61 note: its
    `expected_delta` is derived from the same figure as `actual_delta`, a
    guaranteed-zero-error sample that would dilute the metric) and rows
    with `actual_delta IS NULL` (no write attempted, or unverified with no
    delta recorded)."""
    eligible = [
        r for r in rows if r.kind != "compensate" and r.actual_delta is not None
    ]
    n = len(eligible)
    if n == 0:
        return MetricResult(value=None, n=0)
    exact = sum(1 for r in eligible if r.expected_delta == r.actual_delta)
    return MetricResult(value=exact / n, n=n)


@dataclass(frozen=True)
class WriteDeltaRow:
    """One receipt's recorded delta versus the cart's OWN before/after
    movement (D82).

    Split out from `cost_delta_accuracy`, which compares the delta against
    the price the product SEARCH advertised. That comparison was gated at
    "exact" on an assumption D68 disproved: the cart applies a per-product
    loyalty discount the search does not carry (D76), so the two disagree
    on most receipts no matter how correct the implementation is.

    This one asks the question the project actually controls -- does the
    number we recorded match what the cart did? -- and is gated at 1.00
    absolute. `actual_delta` is `None` on an unverified write, where no
    delta was recorded at all; such a row is EXCLUDED rather than counted
    as a mismatch, because an honest "we do not know" must not be turned
    into a manufactured defect.
    """

    actual_delta: Optional[Decimal]
    cart_delta: Decimal


def write_delta_fidelity(rows: Sequence[WriteDeltaRow]) -> MetricResult:
    eligible = [r for r in rows if r.actual_delta is not None]
    n = len(eligible)
    if n == 0:
        return MetricResult(value=None, n=0)
    # Decimal equality, not string equality: 14.30 and 14.3 are the same
    # money, and a receipt must not fail on trailing-zero formatting.
    matched = sum(1 for r in eligible if r.actual_delta == r.cart_delta)
    return MetricResult(value=matched / n, n=n)


@dataclass(frozen=True)
class RecoveryEpisode:
    """One participant/cart/task/condition episode (plan section 13.1) --
    retries and resumes within one episode do not create a new one."""

    completed: bool


def recovery_completion_rate(episodes: Sequence[RecoveryEpisode]) -> MetricResult:
    n = len(episodes)
    if n == 0:
        return MetricResult(value=None, n=0)
    completed = sum(1 for e in episodes if e.completed)
    return MetricResult(value=completed / n, n=n)


@dataclass(frozen=True)
class DisclosureRow:
    """One session's disclosure outcome. `had_invisible_constraint` is
    `None` when visibility was never independently verified for that
    session -- such a session must be excluded from both the numerator
    and denominator, never folded into "hidden" by a `bool(None)`-style
    shortcut."""

    had_invisible_constraint: Optional[bool]
    visibility_verified: bool


def disclosure_rate(rows: Sequence[DisclosureRow]) -> MetricResult:
    verified = [r for r in rows if r.visibility_verified]
    n = len(verified)
    if n == 0:
        return MetricResult(value=None, n=0)
    with_constraint = sum(1 for r in verified if r.had_invisible_constraint)
    return MetricResult(value=with_constraint / n, n=n)
