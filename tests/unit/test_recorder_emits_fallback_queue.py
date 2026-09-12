"""`_build_draft_from_tape` also populates `mcp_by_tool`,
grouping the same taped responses by bare tool name in call order --
never hand-written, never a second source of truth from the args-keyed
`mcp` queue. Closes the interface-with-no-producer the adversarial review
found in the Revision 1 spec.

Offline throughout: exercises the pure transform against a synthetic
tape -- no live call, no replay, no file write.
"""

from scripts.record_replay_bundle import _build_draft_from_tape


def _synthetic_tape_with_repeated_tool_calls() -> dict:
    return {
        "mcp": [
            ("silpo_get_my_shopping_cart", {}, {"shoppingCartId": "cart-1"}),
            (
                "silpo_find_products_batch",
                {"names": ["query one"]},
                {"products": ["first"]},
            ),
            (
                "silpo_find_products_batch",
                {"names": ["query two"]},
                {"products": ["second"]},
            ),
        ],
        "planner": [{"search_terms": ["x"]}],
        "explainer": [{"action_id": "a1", "guest_text_uk": "x"}],
        "final_status": "awaiting_consent",
    }


def test_mcp_by_tool_groups_responses_by_bare_tool_name_in_call_order() -> None:
    draft = _build_draft_from_tape(_synthetic_tape_with_repeated_tool_calls())

    by_tool = draft["payload"]["mcp_by_tool"]
    assert by_tool["silpo_find_products_batch"] == [
        {"products": ["first"]},
        {"products": ["second"]},
    ]
    # cart_id is pseudonymised by the sanitizer -- check shape, not the
    # literal value, same as the other recorder tests do.
    assert len(by_tool["silpo_get_my_shopping_cart"]) == 1
    assert "shoppingCartId" in by_tool["silpo_get_my_shopping_cart"][0]


def test_mcp_by_tool_entries_are_the_same_sanitized_responses_as_mcp() -> None:
    """The fallback queue is derived from the SAME tape as the args-keyed
    map, never a second hand-maintained source -- every response present
    in `mcp_by_tool` must also appear somewhere in `mcp`'s own values."""
    draft = _build_draft_from_tape(_synthetic_tape_with_repeated_tool_calls())

    payload = draft["payload"]
    all_mcp_responses = [r for queue in payload["mcp"].values() for r in queue]
    for tool_responses in payload["mcp_by_tool"].values():
        for response in tool_responses:
            assert response in all_mcp_responses
