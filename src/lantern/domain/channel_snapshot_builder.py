"""Builds the `ChannelSnapshot`/`item_availability` that `disclosure.py`
declared as an explicit input it never fetches itself. Two data sources,
measured directly from the tracked contract fixture's `outputSchema`, not
assumed:

- `silpo_get_time_slots` alone supplies `min_order_cost`, `delivery_cost`,
  `delivery_cost_map`, `slots_total`, `slots_free`.
- `silpo_find_products_batch`'s `products[].available` field answers the
  open caveat directly — a channel's price/slot match is not itself proof
  the cart's own items sell there.

Pure per this project's "domain core does no I/O" invariant: both functions
below take an already-fetched raw MCP response, never call MCP themselves.
"""

from datetime import datetime
from typing import Any, List, Mapping, Sequence, Tuple

from src.lantern.domain.disclosure import ChannelSnapshot
from src.lantern.domain.evidence_gate import raw_candidates_from_find_products_batch
from src.lantern.domain.models import Money
from src.lantern.domain.normalizer import to_money


class NoTimeSlotsAvailableError(ValueError):
    """No slots came back for this branch/channel combination — there is no
    source for `min_order_cost`/`delivery_cost` at all, and
    `ChannelSnapshot.min_order_cost` is a required field. Fabricating a
    value here would be an invented fact rather than a measured one; the
    caller treats this channel as unavailable instead."""


class AmbiguousTimeSlotDataError(ValueError):
    """Slots for the same branch/channel disagree on `minOrderCost` —
    follows the same fail-safe pattern used at the cart level (a
    disagreeing source is `unverified`, never silently resolved by picking
    one value), applied here to the per-channel snapshot."""


def build_item_availability(
    expected_external_product_ids: Sequence[int],
    find_products_batch_response: Mapping[str, Any],
    call_id: str,
    captured_at: datetime,
) -> List[bool]:
    """Looks up each of the cart's own line-item
    article codes in a `find_products_batch` response scoped to one
    candidate channel. Missing from the response counts as unavailable —
    same as an explicit `available: False`, never silently treated as
    "not checked" or skipped. Reuses the Evidence Gate's own response
    parser (`raw_candidates_from_find_products_batch`) rather than
    re-parsing the same wire shape a second time.
    """
    candidates = raw_candidates_from_find_products_batch(
        call_id=call_id, response=find_products_batch_response, captured_at=captured_at
    )
    by_external_id = {
        c.external_product_id: c
        for c in candidates
        if c.external_product_id is not None
    }
    return [
        (
            by_external_id[product_id].available_raw is True
            if product_id in by_external_id
            else False
        )
        for product_id in expected_external_product_ids
    ]


def build_item_availability_by_name(
    expected_names: Sequence[str],
    find_products_batch_response: Mapping[str, Any],
    call_id: str,
    captured_at: datetime,
) -> List[bool]:
    """Fallback for `build_item_availability` when no confirmed
    `externalProductId` exists for the cart's own line items — measured
    directly (not assumed): the only tracked live cart capture
    (`tests/unit/fixtures/d12_cart_wire_shape.json`) has an empty
    `shipments[].products[]`, so this project has never seen a live line
    item's article code, and `LineItem.product_id` (the cart's own internal
    id) has no confirmed relationship to `find_products_batch`'s
    `externalProductId`. `find_products_batch`'s own description documents
    free-text name search as supported — this is an approximate signal
    (case-insensitive exact match on `name`), not a guaranteed-exact one,
    and stays a named risk until the first live multi-item cart capture
    settles the real id relationship.
    """
    candidates = raw_candidates_from_find_products_batch(
        call_id=call_id, response=find_products_batch_response, captured_at=captured_at
    )
    by_name = {c.name.strip().lower(): c for c in candidates if c.name}
    return [
        (
            by_name[name.strip().lower()].available_raw is True
            if name.strip().lower() in by_name
            else False
        )
        for name in expected_names
    ]


def select_timeslot_for_find_products_batch(
    time_slots_response: Mapping[str, Any],
) -> Tuple[str, str]:
    """`find_products_batch`'s own `inputSchema` requires `timeslotStart`/
    `timeslotEnd` (measured directly); this is where a
    candidate channel's timeslot for that call comes from. Picks the first
    slot with `available: True`; a channel with no free slot at all cannot
    supply this precondition, so this raises the same fail-closed error a
    zero-slot response does — there is nothing to build a proposal against.
    """
    for slot in time_slots_response.get("slots", []):
        if slot.get("available") is True:
            return slot["start"], slot["end"]
    raise NoTimeSlotsAvailableError(
        "no slot with available=True in this channel's time-slots response"
    )


def _money_map_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cost": to_money(entry.get("cost")),
        "fromOrderCost": to_money(entry.get("fromOrderCost")),
    }


def build_channel_snapshot_from_time_slots(
    delivery_type: str,
    branch_id: str,
    branch_is_inferred: bool,
    time_slots_response: Mapping[str, Any],
    item_availability: Sequence[bool] | None = None,
) -> ChannelSnapshot:
    """Builds everything `get_time_slots` alone can supply. `delivery_cost`/
    `delivery_cost_map` are taken from the first slot — these are
    informational display values (peak-hour surcharges can legitimately
    differ by slot), not part of the safety gate, which only reads
    `min_order_cost`/`slots_free`/`item_availability`/`branch_is_inferred`.
    `min_order_cost` IS part of that gate, so slots disagreeing on it fail
    closed rather than picking one arbitrarily (`AmbiguousTimeSlotDataError`).
    """
    slots = time_slots_response.get("slots", [])
    if not slots:
        raise NoTimeSlotsAvailableError(
            f"no slots returned for branch={branch_id!r}, "
            f"delivery_type={delivery_type!r}"
        )

    min_order_costs = {to_money(s.get("minOrderCost")) for s in slots}
    if len(min_order_costs) > 1:
        raise AmbiguousTimeSlotDataError(
            f"slots disagree on minOrderCost for branch={branch_id!r}, "
            f"delivery_type={delivery_type!r}: {sorted(min_order_costs, key=str)}"
        )
    min_order_cost: Money = min_order_costs.pop()  # type: ignore[assignment]

    first_slot = slots[0]
    delivery_cost = to_money(first_slot.get("deliveryCost"))
    delivery_cost_map = [
        _money_map_entry(entry) for entry in first_slot.get("deliveryCostMap", [])
    ]
    slots_free = sum(1 for s in slots if s.get("available") is True)

    return ChannelSnapshot(
        delivery_type=delivery_type,
        branch_id=branch_id,
        branch_is_inferred=branch_is_inferred,
        min_order_cost=min_order_cost,
        delivery_cost=delivery_cost,
        delivery_cost_map=delivery_cost_map,
        slots_total=len(slots),
        slots_free=slots_free,
        item_availability=list(item_availability) if item_availability else None,
    )
