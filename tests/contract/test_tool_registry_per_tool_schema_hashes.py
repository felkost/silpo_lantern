"""D-G5-05: `ToolRegistry.tool_schema_hashes` returns per-tool
(reviewed_hash, live_hash, is_quarantined) -- the exact shape the Write
Guard needs -- distinct from the whole-array `schema_hash` drift tripwire.
"""

import json

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.client import ToolRegistry

FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
)


def _load_tools_raw() -> list:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return envelope["payload"]["tools"]


def test_reviewed_and_live_hash_match_for_an_unmodified_tool() -> None:
    registry = ToolRegistry(fetch=_load_tools_raw, ttl_seconds=60, now=lambda: 0.0)
    reviewed, live, is_quarantined = registry.tool_schema_hashes(
        "silpo_add_or_update_cart_products"
    )
    assert reviewed == live
    assert reviewed != ""
    assert is_quarantined is False


def test_a_modified_tool_object_diverges_from_the_reviewed_hash() -> None:
    tools_raw = _load_tools_raw()
    mutated = [dict(t) for t in tools_raw]
    for t in mutated:
        if t["name"] == "silpo_add_or_update_cart_products":
            t["description"] = t["description"] + " MUTATED"

    registry = ToolRegistry(fetch=lambda: mutated, ttl_seconds=60, now=lambda: 0.0)
    reviewed, live, _ = registry.tool_schema_hashes("silpo_add_or_update_cart_products")
    assert reviewed != live


def test_unrelated_tool_drift_does_not_move_this_tools_hash() -> None:
    """The whole point of per-tool granularity: another tool's release
    note must not make this tool's own hash look drifted."""
    tools_raw = _load_tools_raw()
    mutated = [dict(t) for t in tools_raw]
    for t in mutated:
        if t["name"] == "silpo_get_my_shopping_cart":
            t["description"] = t["description"] + " UNRELATED CHANGE"

    registry = ToolRegistry(fetch=lambda: mutated, ttl_seconds=60, now=lambda: 0.0)
    reviewed, live, _ = registry.tool_schema_hashes("silpo_add_or_update_cart_products")
    assert reviewed == live
