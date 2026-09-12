"""T5: `scripts/record_replay_bundle.py` used to leave
`tool_schema_hashes` empty and both `schema_hash` fields blank "for
hand-filling" -- `BundlePlayer.tool_schema_hashes` then falls back to
`("reviewed-hash", "reviewed-hash", False)` for every tool
(`graph/replay.py`), making a REPLAYED write's schema-drift check
vacuous: any tool, drifted or not, would silently "match". Fixed by
taping a live `tools/list` snapshot alongside the MCP/LLM calls
(`run_capture`) and deriving both fields from it (`run_build`).

Offline throughout: exercises `_build_draft_from_tape`, the pure
transform split out of `run_build`, against a synthetic tape -- no live
call, no replay, no file write.
"""

from src.lantern.mcp.client import compute_per_tool_schema_hashes, compute_schema_hash
from scripts.record_replay_bundle import _build_draft_from_tape

_SYNTHETIC_TOOL = {
    "name": "silpo_add_or_update_cart_products",
    "description": "x",
    "inputSchema": {"type": "object", "properties": {}},
}


def _synthetic_tape(*, with_tools_list: bool) -> dict:
    tape = {
        "mcp": [
            (
                "silpo_get_my_shopping_cart",
                {},
                {"shoppingCartId": "cart-1"},
            )
        ],
        "planner": [{"search_terms": ["x"]}],
        "explainer": [{"action_id": "a1", "guest_text_uk": "x"}],
        "final_status": "awaiting_consent",
    }
    if with_tools_list:
        tape["tools_list"] = [_SYNTHETIC_TOOL]
    return tape


def test_tool_schema_hashes_and_schema_hash_are_filled_when_tools_list_is_taped() -> (
    None
):
    draft = _build_draft_from_tape(_synthetic_tape(with_tools_list=True))

    assert draft["source_schema_hash"] != ""
    assert draft["source_schema_hash"] == compute_schema_hash([_SYNTHETIC_TOOL])
    assert draft["payload"]["versions"]["schema_hash"] == draft["source_schema_hash"]

    tool_hashes = draft["payload"]["tool_schema_hashes"]
    assert tool_hashes, "tool_schema_hashes must not be empty"
    expected = compute_per_tool_schema_hashes([_SYNTHETIC_TOOL])
    for name, expected_hash in expected.items():
        reviewed, live, quarantined = tool_hashes[name]
        assert reviewed == expected_hash
        assert live == expected_hash
        assert quarantined is False


def test_an_older_tape_without_tools_list_still_builds_with_empty_hashes() -> None:
    """A raw tape recorded BEFORE this fix has no `tools_list` key -- it
    must still build (never crash), leaving the fields empty exactly as
    the pre-fix behaviour did, not silently fabricating a hash."""
    draft = _build_draft_from_tape(_synthetic_tape(with_tools_list=False))
    assert draft["source_schema_hash"] == ""
    assert draft["payload"]["versions"]["schema_hash"] == ""
    assert draft["payload"]["tool_schema_hashes"] == {}
