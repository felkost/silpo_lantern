"""A7/D6/D10: the disclosure layer, including the delivery-channel
comparison. Read-only, pure arithmetic over data the caller already
fetched — this module never calls MCP itself (D-G3-04): `ChannelSnapshot`
is an explicit input, and fetching per-channel data (`get_available_delivery_types`,
`get_time_slots`) is G4's graph work.
"""

from typing import Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from src.lantern.domain.diagnosis import compute_order_cost_min_gap
from src.lantern.domain.models import Cart, Diagnosis, Money, Validation


class DisclosureReport(BaseModel):
    """Everything the cart already carries, including validations the
    app's own UI does not render (plan section 5.1's hero requirement)."""

    model_config = ConfigDict(frozen=True)

    blockers: list[Validation]
    disclosures: list[Validation]
    gap: Optional[Money]
    gap_is_borderline: bool


class ChannelSnapshot(BaseModel):
    """One delivery channel's measured state. `branch_is_inferred=True`
    (D10: the current channel's branch was guessed, not confirmed by a
    live call) and `item_availability=None` (never checked) both force a
    `needs_check` verdict regardless of price/slot numbers — G3-F8/F9."""

    model_config = ConfigDict(frozen=True)

    delivery_type: str
    branch_id: str
    branch_is_inferred: bool
    min_order_cost: Money
    delivery_cost: Optional[Money]
    delivery_cost_map: list[dict[str, Money]]
    slots_total: int
    slots_free: int
    item_availability: Optional[list[bool]] = None


class ChannelComparisonRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot: ChannelSnapshot
    gap: Money
    verdict: Literal["clears_now", "needs_check"]
    reason: str


def build_disclosure(cart: Cart, diagnosis: Diagnosis) -> DisclosureReport:
    return DisclosureReport(
        blockers=[b.validation for b in diagnosis.blockers],
        disclosures=diagnosis.disclosures,
        gap=diagnosis.gap,
        gap_is_borderline=diagnosis.gap_is_borderline,
    )


def compare_channels(
    current_products_total: Money, snapshots: Sequence[ChannelSnapshot]
) -> list[ChannelComparisonRow]:
    """D10/D-G3-05: a row reads `clears_now` only when the gap already
    clears (<=0) AND item availability was actually checked (all True) AND
    the branch is a real, confirmed one AND at least one slot is free.
    Any missing piece is `needs_check`, with the specific reason named —
    never silently upgraded to `clears_now` on partial evidence."""
    rows: list[ChannelComparisonRow] = []
    for snapshot in snapshots:
        gap = compute_order_cost_min_gap(
            snapshot.min_order_cost, current_products_total
        )
        gap_value = Money(gap)

        reasons: list[str] = []
        if gap_value > 0:
            reasons.append("does_not_clear_threshold")
        if snapshot.branch_is_inferred:
            reasons.append("branch_is_inferred")
        if snapshot.item_availability is None:
            reasons.append("item_availability_not_checked")
        elif not all(snapshot.item_availability):
            reasons.append("some_items_unavailable_on_this_channel")
        if snapshot.slots_free <= 0:
            reasons.append("no_free_slots")

        if reasons:
            rows.append(
                ChannelComparisonRow(
                    snapshot=snapshot,
                    gap=gap_value,
                    verdict="needs_check",
                    reason=",".join(reasons),
                )
            )
        else:
            rows.append(
                ChannelComparisonRow(
                    snapshot=snapshot,
                    gap=gap_value,
                    verdict="clears_now",
                    reason="",
                )
            )
    return rows
