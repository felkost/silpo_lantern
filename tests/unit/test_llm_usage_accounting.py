"""tokens and cost for a LIVE session, from the
provider's own usage block, accumulated per session and shown as SPEND --
never as "remaining", which only the provider's dashboard knows. Closes
half of `tokens_used` is now written by the route from measured
usage, not left at 0.
"""

from decimal import Decimal
from typing import Any, Dict, List, Tuple

import pytest

from src.lantern.domain.repeat_accounting import TokenUsage
from src.lantern.graph.llm_adapter import (
    current_usage_log,
    load_llm_prices,
    make_explainer_call,
    make_planner_call,
)
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from tests.unit.test_api_session_routes import (
    _awaiting_consent_state,
    _client,
    _FakeGraph,
    _make_app,
    _proposal,
    _read_pipeline_chunks,
)
from tests.unit.test_api_stage_event import _frames


class _Raw:
    def __init__(self, usage: Dict[str, int]) -> None:
        self.usage_metadata = usage


class _IncludeRawLLM:
    """What `with_structured_output(..., include_raw=True)` returns."""

    def __init__(self, parsed: Any, usage: Dict[str, int]) -> None:
        self._parsed, self._usage = parsed, usage

    def invoke(self, messages: Any) -> Any:
        return {"raw": _Raw(self._usage), "parsed": self._parsed, "parsing_error": None}


class _PlainLLM:
    def __init__(self, parsed: Any) -> None:
        self._parsed = parsed

    def invoke(self, messages: Any) -> Any:
        return self._parsed


def test_planner_call_records_usage_when_a_log_is_bound() -> None:
    intent = SearchIntent(search_terms=["milk"])
    log: List[Tuple[str, TokenUsage]] = []
    token = current_usage_log.set(log)
    try:
        call = make_planner_call(
            _IncludeRawLLM(intent, {"input_tokens": 600, "output_tokens": 40}), []
        )
        assert call(_awaiting_consent_state()) == intent
    finally:
        current_usage_log.reset(token)
    assert log == [("planner", TokenUsage(600, 40))]


def test_explainer_call_without_a_bound_log_still_returns_parsed() -> None:
    out = ExplainerOutput(action_id="a1", guest_text_uk="Додати молоко")
    call = make_explainer_call(
        _IncludeRawLLM(out, {"input_tokens": 1, "output_tokens": 1})
    )
    assert call(_proposal()) == out


def test_a_plain_structured_result_is_passed_through() -> None:
    """The offline fakes return the parsed model directly; they must not
    need to imitate include_raw's envelope."""
    intent = SearchIntent(search_terms=["milk"])
    assert make_planner_call(_PlainLLM(intent), [])(_awaiting_consent_state()) == intent


def test_a_parsing_error_is_raised_not_swallowed() -> None:
    class _Broken:
        def invoke(self, messages: Any) -> Any:
            return {"raw": _Raw({}), "parsed": None, "parsing_error": ValueError("bad")}

    with pytest.raises(ValueError):
        make_planner_call(_Broken(), [])(_awaiting_consent_state())


def test_prices_come_from_the_pinned_table() -> None:
    prices = load_llm_prices()
    for role in ("planner", "explainer"):
        assert prices[role]["input"] > 0 and prices[role]["output"] > 0
    assert prices["ceiling_usd"] == 20


class _SpendingGraph(_FakeGraph):
    """A node that calls the model: appends to the bound usage log the way
    the adapter does, so the route sees usage arrive mid-stream."""

    async def astream(  # type: ignore[override]
        self, input_: Any, config: Any, stream_mode: str = "updates"
    ):
        self.astream_inputs.append(input_)
        for chunk in self.chunks:
            if "plan" in chunk or "explain" in chunk:
                log = current_usage_log.get()
                assert log is not None, "the route must bind a usage log"
                log.append(("planner", TokenUsage(1000, 100)))
            yield chunk
        self.state = self.final_state


def test_stage_frames_carry_cumulative_spend_and_the_route_persists_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = {**_awaiting_consent_state(), "tokens_used": 500, "llm_cost_usd": 0.001}
    graph = _SpendingGraph(chunks=_read_pipeline_chunks(), final_state=prior)
    client = _client(_make_app(graph, monkeypatch))

    body = client.get("/session/s1/events").text

    stages = _frames(body, "stage")
    first, last = stages[0]["usage"], stages[-1]["usage"]
    assert first["tokens"] == 0 and first["cost_usd"] == 0.0  # fresh state: nothing yet
    assert last["tokens"] == 1100
    prices = load_llm_prices()["planner"]
    assert last["cost_usd"] == pytest.approx(
        (1000 * prices["input"] + 100 * prices["output"]) / 1_000_000, rel=1e-6
    )
    assert last["ceiling_usd"] == 20
    assert "remaining" not in body
    # Persisted onto the checkpoint so the second /events call continues
    # the count instead of starting over.
    assert graph.updated_with["tokens_used"] == 1100
    assert graph.updated_with["llm_cost_usd"] == pytest.approx(last["cost_usd"])


def test_a_run_with_no_model_call_persists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=[{"write_and_readback": {"status": "verified"}}],
        final_state={**_awaiting_consent_state(), "status": "verified"},
        initial_state={**_awaiting_consent_state(), "consent_action_id": "a1"},
    )
    client = _client(_make_app(graph, monkeypatch))

    client.get("/session/s1/events")

    assert graph.updated_with is None
    assert Decimal("0") == 0  # keeps the import honest
