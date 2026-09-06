"""D-G5-05: `ToolRegistry.tool_schema_hashes` returns per-tool
(reviewed_hash, live_hash, is_quarantined) -- the exact shape the Write
Guard needs -- distinct from the whole-array `schema_hash` drift tripwire.
"""

import json

from mcp import types as mcp_types

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.client import ToolRegistry, compute_per_tool_schema_hashes

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


def test_hash_is_identical_whether_input_is_raw_or_sdk_round_tripped() -> None:
    """The property whose absence refused this project's first real write.

    `ToolRegistry.fetch` returns raw wire dicts here and SDK-round-tripped
    dicts in production (`mcp.session.list_tools_raw` can only obtain typed
    `Tool` objects). While the canonicalisation lived in the caller rather
    than in `compute_per_tool_schema_hashes`, those two forms hashed
    differently, so a reviewed baseline built from one could never match a
    live listing from the other -- and the Write Guard correctly, but
    uselessly, refused an unchanged schema.
    """
    raw = _load_tools_raw()
    round_tripped = [
        mcp_types.Tool.model_validate(t).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        for t in raw
    ]

    assert compute_per_tool_schema_hashes(raw) == compute_per_tool_schema_hashes(
        round_tripped
    )


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
