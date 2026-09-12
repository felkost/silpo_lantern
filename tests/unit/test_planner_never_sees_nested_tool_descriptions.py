"""a tool's own description is untrusted
input at EVERY level, not only the top level. `tool_view.py`'s own
`PLANNER_TOOL_PARAPHRASES` already replaces the top-level description,
but `build_planner_tool_view` passed `inputSchema` through raw --
`llm_adapter.render_planner_prompt` then serialises it verbatim into the
prompt, so a server-authored imperative inside a PROPERTY description
reached the planner today (measured: `silpo_get_product_details`'s
`slug` property literally says "MUST be taken from ... Never construct
from name" -- and the four reviewed tools carry similar imperatives
in their weighted-unit and min-order-cost fields).

Parametrised over both tracked fixtures, since the drift itself only
touched some tools -- the guarantee must hold regardless of which
snapshot is live.
"""

import json

import pytest

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.tool_view import build_planner_tool_view

_FIXTURES = [
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json",
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-07.json",
]


def _tools_raw(fixture_path):
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return payload["payload"]["tools"]


@pytest.mark.parametrize("fixture_path", _FIXTURES, ids=[p.name for p in _FIXTURES])
def test_no_nested_description_survives_into_the_planner_view(fixture_path) -> None:
    view = build_planner_tool_view(_tools_raw(fixture_path))
    assert view, "the planner-visible tool set must not be empty"

    def _find_description_keys(node) -> list:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "description":
                    found.append(value)
                found.extend(_find_description_keys(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(_find_description_keys(item))
        return found

    for tool in view:
        leaked = _find_description_keys(tool.input_schema)
        assert leaked == [], f"{tool.name} leaks nested descriptions: {leaked}"


@pytest.mark.parametrize("fixture_path", _FIXTURES, ids=[p.name for p in _FIXTURES])
def test_the_schema_shape_survives_stripping(fixture_path) -> None:
    """Stripping descriptions must not drop the actual schema -- types,
    `required`, and property names all stay, since the planner still
    needs to know the tool's real argument shape."""
    view = build_planner_tool_view(_tools_raw(fixture_path))
    by_name = {tool.name: tool for tool in view}
    details = by_name.get("silpo_get_product_details")
    assert details is not None
    assert set(details.input_schema["properties"]) == {
        "branchId",
        "slug",
        "deliveryType",
        "timeslotStart",
        "timeslotEnd",
    }
    assert details.input_schema["required"] == [
        "branchId",
        "slug",
        "deliveryType",
        "timeslotStart",
        "timeslotEnd",
    ]
    assert details.input_schema["properties"]["slug"]["type"] == "string"
