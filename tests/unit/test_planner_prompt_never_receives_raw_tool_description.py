"""The planner
never receives a raw tool description string — only name, a reviewed
one-line paraphrase, and the JSON Schema shape survive into what the LLM
sees. Asserted against the CORRECTED verbatim string, read
from the tracked contract fixture — never re-typed into this test body,
which is exactly how the string ended up wrong in three other documents.
"""

import json

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.tool_view import (
    PLANNER_TOOL_PARAPHRASES,
    build_planner_tool_view,
)

FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
)


def _load_tools_raw() -> list:
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return envelope["payload"]["tools"]


def test_the_live_budget_instruction_string_never_appears_in_the_planner_view() -> None:
    tools_raw = _load_tools_raw()
    live_description = next(
        t["description"] for t in tools_raw if t["name"] == "silpo_find_products_batch"
    )
    assert "BUDGET" in live_description  # sanity: the fixture still has it

    view = build_planner_tool_view(tools_raw)
    rendered = json.dumps([v.__dict__ for v in view], ensure_ascii=False)

    assert live_description not in rendered
    assert "BUDGET" not in rendered
    assert "Maximize the total spend" not in rendered


def test_no_raw_description_field_from_any_tool_survives_into_the_view() -> None:
    """Broader than the one BUDGET string — no tool's live `description`
    text appears anywhere in what the planner sees, not just the one
    already-known adversarial example."""
    tools_raw = _load_tools_raw()
    view = build_planner_tool_view(tools_raw)
    rendered = json.dumps([v.__dict__ for v in view], ensure_ascii=False)

    for tool in tools_raw:
        description = tool.get("description")
        if description and len(description) > 20:
            assert description not in rendered


def test_only_tools_with_a_reviewed_paraphrase_are_exposed_at_all() -> None:
    """A tool absent from `PLANNER_TOOL_PARAPHRASES` is excluded entirely —
    never shown with a generic fallback description, which would just move
    the untrusted-text problem one step sideways."""
    tools_raw = _load_tools_raw()
    view = build_planner_tool_view(tools_raw)

    exposed_names = {v.name for v in view}
    assert exposed_names == set(PLANNER_TOOL_PARAPHRASES.keys())
    assert exposed_names <= {t["name"] for t in tools_raw}


def test_a_synthetic_unreviewed_tool_is_never_exposed() -> None:
    tools_raw = [
        {
            "name": "silpo_totally_new_write_tool",
            "description": "some description",
            "inputSchema": {"type": "object"},
        }
    ]
    view = build_planner_tool_view(tools_raw)
    assert view == []


def test_exposed_tools_still_carry_their_real_input_schema() -> None:
    """Stripping the description must not also strip the JSON Schema shape
    the planner needs to actually call the tool correctly."""
    tools_raw = _load_tools_raw()
    view = build_planner_tool_view(tools_raw)

    find_products = next(v for v in view if v.name == "silpo_find_products_batch")
    assert "required" in find_products.input_schema
    assert "timeslotStart" in find_products.input_schema["required"]
