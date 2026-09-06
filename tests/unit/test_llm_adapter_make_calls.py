"""`make_planner_call`/`make_explainer_call` never construct a live
`ChatOpenAI` themselves — they take an already-built
`StructuredLLM` (anything with `.invoke(messages) -> T`), so both are
testable with a fake, entirely offline. `build_planner_llm`/
`build_explainer_llm` (the functions that DO construct a real client) are
never called here or by any other automated test — see `llm_adapter.py`'s
own module docstring.
"""

from datetime import datetime, timezone
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage

from src.lantern.domain.models import ActionProposal, EvidenceTuple
from src.lantern.graph.llm_adapter import make_explainer_call, make_planner_call
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import new_recovery_state


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.received_messages = None

    def invoke(self, messages):
        self.received_messages = messages
        return self.response


def test_planner_call_sends_system_and_human_messages_and_returns_the_llm_result() -> (
    None
):
    canned = SearchIntent(search_terms=["молоко"], quantity_hint=1)
    fake_llm = _FakeLLM(canned)
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )

    planner_call = make_planner_call(fake_llm, tools_raw=[])
    result = planner_call(state)

    assert result is canned
    assert len(fake_llm.received_messages) == 2
    assert isinstance(fake_llm.received_messages[0], SystemMessage)
    assert isinstance(fake_llm.received_messages[1], HumanMessage)
    assert "reasoning component of Lantern" in fake_llm.received_messages[0].content


def test_explainer_call_sends_system_and_human_messages_and_returns_result() -> None:
    canned = ExplainerOutput(action_id="a1", guest_text_uk="Додайте молоко.")
    fake_llm = _FakeLLM(canned)
    evidence = EvidenceTuple(
        product_id="1",
        price=Decimal("39.99"),
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=datetime.now(timezone.utc),
    )
    proposal = ActionProposal(
        action_id="a1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Молоко",
        quantity=Decimal("1"),
        expected_delta=Decimal("39.99"),
        canonical_args={"productId": "1"},
        evidence=[evidence],
    )

    explainer_call = make_explainer_call(fake_llm)
    result = explainer_call(proposal)

    assert result is canned
    assert len(fake_llm.received_messages) == 2
    assert "39.99" in fake_llm.received_messages[1].content


def test_planner_call_never_leaks_the_live_budget_instruction_string() -> None:
    """End-to-end through the real adapter: the corrected verbatim
    "BUDGET" string from the tracked contract fixture must not reach the
    planner's rendered prompt, even when a raw tool carrying it is passed
    into `tools_raw`."""
    import json

    fixture_path = "tests/contract/fixtures/tools_list_2026-09-05.json"
    envelope = json.load(open(fixture_path, encoding="utf-8"))
    tools_raw = envelope["payload"]["tools"]

    canned = SearchIntent(search_terms=["x"])
    fake_llm = _FakeLLM(canned)
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )

    planner_call = make_planner_call(fake_llm, tools_raw=tools_raw)
    planner_call(state)

    human_content = fake_llm.received_messages[1].content
    assert "BUDGET" not in human_content
    assert "Maximize the total spend" not in human_content
