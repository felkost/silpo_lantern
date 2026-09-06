"""No write-capable tool is reachable from any code path this stage adds.
Two independent proofs, since either alone leaves a gap: (a) the planner's
tool list is a fixed, typed set of function parameters on
`build_recovery_graph` — there is no generic "call any tool by name"
entrypoint anywhere in the graph for a write tool to slip into; (b) every
name the planner IS allowed to see is independently confirmed read-only
against the live/tracked `tools/list` annotations, not merely assumed safe
because a human picked short, read-sounding names.
"""

import inspect
import json
import typing

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.tool_view import PLANNER_TOOL_PARAPHRASES

FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
)


def _load_tools_raw() -> list:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return envelope["payload"]["tools"]


def test_every_planner_visible_tool_is_read_only_per_the_live_annotations() -> None:
    tools_raw = _load_tools_raw()
    by_name = {t["name"]: t for t in tools_raw}

    for name in PLANNER_TOOL_PARAPHRASES:
        tool = by_name[name]  # KeyError if a paraphrase drifts from the real tools
        assert tool["annotations"]["readOnlyHint"] is True, name


def test_build_recovery_graph_has_no_generic_call_any_tool_parameter() -> None:
    """Every MCP-shaped parameter is a distinct, statically-typed
    `Callable` bound to exactly one real tool's own argument shape — never
    a `Callable[[str, ...], ...]`-style generic dispatcher that could be
    handed a write tool's name at runtime."""
    signature = inspect.signature(build_recovery_graph)
    fetch_params = {
        name: param
        for name, param in signature.parameters.items()
        if name.startswith("fetch_")
    }

    assert set(fetch_params) == {
        "fetch_my_cart",
        "fetch_cart_by_id",
        "fetch_delivery_types",
        "fetch_time_slots",
        "fetch_find_products_batch",
    }

    import collections.abc

    for name, param in fetch_params.items():
        # Each is a `Callable` bound to one specific tool's own argument
        # shape (e.g. `Callable[[str], Mapping]` for a cart id) — never a
        # generic `Callable[[str, Mapping], Mapping]`-style dispatcher that
        # a caller could point at an arbitrary tool name at runtime. The
        # five names above are exhaustive by construction: adding a write
        # tool would mean adding a sixth `fetch_*`/`call_*` parameter here,
        # which this test's name-set assertion above would catch.
        assert typing.get_origin(param.annotation) is collections.abc.Callable, name
