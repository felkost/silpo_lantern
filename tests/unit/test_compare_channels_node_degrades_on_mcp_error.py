"""A live run against the hero cart found a
real gap: `silpo_get_available_delivery_types` returned a channel option
with no `branchId` (a documented case was SelfPickup; live, NovaPoshta
did too) — `fetch_time_slots("", [delivery_type])` then failed live with a
real `McpToolExecutionError` ("Resource not found"). `compare_channels_
node`'s own docstring says a channel it "cannot safely build a snapshot
for... is simply excluded from the comparison — degraded, not a reason to
abort the whole recovery" — but the code only caught the domain-level
`NoTimeSlotsAvailableError`, never an MCP-level failure, so a live channel
error crashed the entire graph run instead of just dropping that channel.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import Cart
from src.lantern.graph.nodes import make_compare_channels_node
from src.lantern.graph.state import RecoveryState, new_recovery_state
from src.lantern.mcp.errors import McpToolExecutionError

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

_DELIVERY_TYPES_RESPONSE = {
    "success": True,
    "summary": "",
    "options": [
        {"deliveryType": "NovaPoshta"},  # no branchId, like the live finding
        {"deliveryType": "SelfPickup", "branchId": "b-ok"},
    ],
}

_TIME_SLOTS_RESPONSE = {
    "slots": [
        {
            "start": "2026-09-08T10:00:00Z",
            "end": "2026-09-08T12:00:00Z",
            "available": True,
            "deliveryType": "SelfPickup",
            "deliveryCost": 0,
            "deliveryCostMap": [],
            "minOrderCost": 199,
        }
    ]
}


def _cart() -> Cart:
    return Cart(
        cart_id="cart-1",
        products_total=Decimal("404.89"),
        latitude=50.45,
        longitude=30.52,
        products=[],
    )


def _state() -> RecoveryState:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    state["cart"] = _cart()
    return state


def test_an_mcp_error_on_one_channel_degrades_that_channel_not_the_whole_node() -> None:
    def fetch_time_slots(branch_id: str, types):
        if branch_id == "":
            # The exact live failure: an empty/unresolved branchId is
            # rejected server-side, not silently returning empty slots.
            raise McpToolExecutionError(content="Resource not found")
        return _TIME_SLOTS_RESPONSE

    node = make_compare_channels_node(
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=fetch_time_slots,
        fetch_find_products_batch=lambda *a, **kw: {"queries": []},
        now=lambda: _NOW,
    )

    result = node(_state())

    assert result["channel_comparison"] is not None
    snapshots = result["channel_snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0].delivery_type == "SelfPickup"
