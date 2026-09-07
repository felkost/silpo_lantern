"""Typed wrappers binding `mcp.session.call_tool` to each of the graph's
required `Callable` signatures. Closes the G4-carried risk this project's
own stage reports named twice: "live MCP fetchers are proven live
(`scripts/g4_live_evidence_gate_run.py`) but not wired into any production
entry point." `apps/api` needs a real graph to serve `/session` from --
these functions are that wiring, one per read tool plus the single write
tool, never a generic "call any tool" dispatcher.

Argument shapes measured directly from
`tests/contract/fixtures/tools_list_2026-09-05.json`'s own `inputSchema`
per tool, not paraphrased.
"""

from typing import Any, Dict, Mapping, Sequence

from src.lantern.mcp.session import call_tool


def fetch_my_cart() -> Mapping[str, Any]:
    return call_tool("silpo_get_my_shopping_cart", {})


def fetch_cart_by_id(cart_id: str) -> Mapping[str, Any]:
    return call_tool("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id})


def fetch_delivery_types(latitude: float, longitude: float) -> Mapping[str, Any]:
    return call_tool(
        "silpo_get_available_delivery_types",
        {"latitude": latitude, "longitude": longitude},
    )


def fetch_time_slots(
    branch_id: str, delivery_types: Sequence[str]
) -> Mapping[str, Any]:
    return call_tool(
        "silpo_get_time_slots",
        {"branchId": branch_id, "deliveryTypes": list(delivery_types)},
    )


def fetch_find_products_batch(
    branch_id: str,
    delivery_type: str,
    timeslot_start: str,
    timeslot_end: str,
    products: Sequence[str],
) -> Mapping[str, Any]:
    return call_tool(
        "silpo_find_products_batch",
        {
            "branchId": branch_id,
            "deliveryType": delivery_type,
            "timeslotStart": timeslot_start,
            "timeslotEnd": timeslot_end,
            "products": list(products),
        },
    )


def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """The one write-capable callable this module exposes -- its own
    argument shape is whatever `authorize_write` already validated before
    this is ever reached (`WRITE_TOOL_ALLOWLIST`); this function itself
    does not decide which tool may be called, it only makes the one real
    network call."""
    return call_tool(tool_name, args)
