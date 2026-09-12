"""`POST /session` is unauthenticated and the LLM
budget is the author's, so session creation is capped per IP per day and
live graph starts are capped per day. Both refuse with 429 and a plain
message before anything reaches the provider.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.limits import SpendCaps
from apps.api.session_cookie import SESSION_COOKIE
from tests.unit.test_api_session_routes import (
    _awaiting_consent_state,
    _FakeGraph,
    _make_app,
    _read_pipeline_chunks,
)


def test_per_ip_cap_counts_one_day_and_resets_on_the_next() -> None:
    now = [0.0]
    caps = SpendCaps(sessions_per_ip=2, llm_runs_per_day=100, clock=lambda: now[0])

    assert caps.admit_session("1.1.1.1")
    assert caps.admit_session("1.1.1.1")
    assert not caps.admit_session("1.1.1.1")
    assert caps.admit_session("2.2.2.2")  # another guest is unaffected
    now[0] += 86_400
    assert caps.admit_session("1.1.1.1")


def test_daily_llm_ceiling() -> None:
    now = [0.0]
    caps = SpendCaps(sessions_per_ip=100, llm_runs_per_day=1, clock=lambda: now[0])

    assert caps.admit_llm_run()
    assert not caps.admit_llm_run()
    now[0] += 86_400
    assert caps.admit_llm_run()


def _client(monkeypatch: pytest.MonkeyPatch, graph: Any, caps: SpendCaps) -> TestClient:
    app = _make_app(graph, monkeypatch)
    app.state.spend_caps = caps
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(SESSION_COOKIE, "s1")
    return client


def test_create_session_refuses_past_the_per_ip_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(chunks=[], final_state={})
    client = _client(
        monkeypatch, graph, SpendCaps(sessions_per_ip=1, llm_runs_per_day=9)
    )

    assert client.post("/session").status_code == 200
    refused = client.post("/session")

    assert refused.status_code == 429
    assert refused.json()["detail"]


def test_events_refuses_a_fresh_run_past_the_daily_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    caps = SpendCaps(sessions_per_ip=9, llm_runs_per_day=0)
    client = _client(monkeypatch, graph, caps)

    refused = client.get("/session/s1/events")

    assert refused.status_code == 429
    assert graph.astream_inputs == []  # nothing ran, nothing was billed


def test_a_resumed_session_is_not_a_second_llm_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling counts graph STARTS -- a repeated GET on an existing
    checkpoint replays, it does not spend."""
    graph = _FakeGraph(
        chunks=[],
        final_state=_awaiting_consent_state(),
        initial_state=_awaiting_consent_state(),
    )
    client = _client(
        monkeypatch, graph, SpendCaps(sessions_per_ip=9, llm_runs_per_day=0)
    )

    assert client.get("/session/s1/events").status_code == 200
