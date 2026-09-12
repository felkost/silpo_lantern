"""T13: every write-kind tool name, and
`silpo_clear_shopping_cart`, must never appear in the planner's own
visible tool set -- `silpo_remove_cart_products` did not drift, so
the drift review does not cover it, and "carries a reviewed hash" is the
weaker bar `tool_view.py` itself distinguishes from a human-approved
paraphrase (`PLANNER_TOOL_PARAPHRASES`). No path was found by which the
planner could reach a write-capable tool through the live schema; this
pins that as a checked property, over both tracked fixtures, rather than
leaving it as an unverified absence.
"""

import json

import pytest

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.tool_view import build_planner_tool_view
from src.lantern.safety.write_guard import (
    COMPENSATION_TOOL_ALLOWLIST,
    WRITE_TOOL_ALLOWLIST,
)

_FIXTURES = [
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json",
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-07.json",
]

_NEVER_PLANNER_VISIBLE = (
    WRITE_TOOL_ALLOWLIST | COMPENSATION_TOOL_ALLOWLIST | {"silpo_clear_shopping_cart"}
)


@pytest.mark.parametrize("fixture_path", _FIXTURES, ids=[p.name for p in _FIXTURES])
def test_write_kind_tools_never_appear_in_the_planner_view(fixture_path) -> None:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    view = build_planner_tool_view(payload["payload"]["tools"])
    visible_names = {tool.name for tool in view}
    assert visible_names.isdisjoint(_NEVER_PLANNER_VISIBLE), (
        visible_names & _NEVER_PLANNER_VISIBLE
    )
