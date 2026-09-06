"""A new or changed tool must be quarantined until reviewed, never
auto-trusted, and there was no enforcement of that for tools before this.
`ToolRegistry._refresh()`'s `unknown_to_registry` only tracks names relative
to in-process memory, which resets on every restart — a tool that appeared
*between* deployments is not "new" to a fresh process. `quarantined` is
checked against the tracked baseline in `src/lantern/mcp/reviewed_tools.json`
instead, which survives a restart.

Drift is deliberately non-fatal: a quarantined tool is simply absent from
what the graph can use; the read path on the reviewed set is unaffected.
"""

from typing import Any, Dict, List

from src.lantern.mcp.client import ToolRegistry, load_reviewed_tool_names


def _list_tools_raw(*names: str) -> List[Dict[str, Any]]:
    return [{"name": name, "inputSchema": {"type": "object"}} for name in names]


def test_a_reviewed_tool_is_never_quarantined() -> None:
    reviewed = load_reviewed_tool_names()
    known_reviewed_name = next(iter(reviewed))
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(known_reviewed_name),
        ttl_seconds=900,
        now=lambda: 0.0,
    )

    cached = registry.get()

    assert cached.quarantined == frozenset()


def test_an_unreviewed_tool_name_is_quarantined_even_on_the_first_fetch() -> None:
    """Unlike `unknown_to_registry` (which never flags anything on a
    process's first-ever fetch — there is nothing to compare against yet),
    quarantine is checked against the tracked baseline from fetch one,
    because the baseline does not depend on process history."""
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw("silpo_totally_unreviewed_tool"),
        ttl_seconds=900,
        now=lambda: 0.0,
    )

    cached = registry.get()

    assert cached.quarantined == frozenset({"silpo_totally_unreviewed_tool"})


def test_mixed_response_quarantines_only_the_unreviewed_names() -> None:
    reviewed = load_reviewed_tool_names()
    known_reviewed_name = next(iter(reviewed))
    registry = ToolRegistry(
        fetch=lambda: _list_tools_raw(known_reviewed_name, "silpo_brand_new_tool"),
        ttl_seconds=900,
        now=lambda: 0.0,
    )

    cached = registry.get()

    assert cached.quarantined == frozenset({"silpo_brand_new_tool"})
    # the reviewed set still completes normally alongside the quarantined one
    assert len(cached.result.tools) == 2
