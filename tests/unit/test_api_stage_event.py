"""G10 delivery C (A-G10-01): the sixth SSE event, `stage` -- one frame per
graph node the stream actually observed, `{node, io}`, in arrival order.
An append-only log of what ran, never a checklist of what should run:
a compensation round enters `write_guard` directly, `retry` returns to
`diagnose`, and an aborted `read` ends the run -- so no index, no pending
rows, no start signal (stream_mode="updates" reports completions only).
"""

import json
import re
from typing import Any, Dict, List

import pytest

from apps.api.routes import NODE_IO
from tests.unit.test_api_session_routes import (
    _awaiting_consent_state,
    _client,
    _consented_state,
    _FakeGraph,
    _make_app,
    _read_pipeline_chunks,
)


def _frames(body: str, event: str) -> List[Dict[str, Any]]:
    return [
        json.loads(m)
        for m in re.findall(rf"event: {event}\ndata: (.*?)\n\n", body, re.S)
    ]


def _events_in_order(body: str) -> List[str]:
    return re.findall(r"event: (\w+)\n", body)


def test_one_stage_per_observed_node_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _FakeGraph(
        chunks=_read_pipeline_chunks(), final_state=_awaiting_consent_state()
    )
    client = _client(_make_app(graph, monkeypatch))

    body = client.get("/session/s1/events").text

    stages = _frames(body, "stage")
    assert [s["node"] for s in stages] == [
        "read",
        "diagnose",
        "compare_channels",
        "explain",
    ]
    assert [s["io"] for s in stages] == [
        NODE_IO["read"],
        NODE_IO["diagnose"],
        NODE_IO["compare_channels"],
        NODE_IO["explain"],
    ]
    assert all(s["session_id"] == "s1" for s in stages)
    # The feed leads the result: a node's stage precedes the frame built
    # from it.
    order = _events_in_order(body)
    assert order.index("stage") < order.index("diagnosis")


def test_every_graph_node_has_an_io_kind() -> None:
    assert set(NODE_IO) == {
        "read",
        "diagnose",
        "compare_channels",
        "plan",
        "collect_and_gate",
        "rank",
        "explain",
        "write_guard",
        "write_and_readback",
        "persist_receipt",
    }
    assert set(NODE_IO.values()) <= {"mcp", "llm", "db", "pure", "mcp+db"}


def test_a_node_that_updates_nothing_still_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`{node: None}` is what a node returning `{}` looks like in
    `stream_mode="updates"`; the falsy guard drops it from every OTHER
    frame, but the feed must not lose a node that ran."""
    graph = _FakeGraph(
        chunks=[
            {"write_and_readback": {"status": "verified"}},
            {"persist_receipt": None},
        ],
        final_state={**_consented_state(), "status": "verified"},
        initial_state=_consented_state(),
    )
    client = _client(_make_app(graph, monkeypatch))

    stages = _frames(client.get("/session/s1/events").text, "stage")

    assert [s["node"] for s in stages] == ["write_and_readback", "persist_receipt"]


def test_a_replayed_get_emits_no_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing ran on a repeat GET at the consent pause; silence is the
    honest output."""
    graph = _FakeGraph(
        chunks=[],
        final_state=_awaiting_consent_state(),
        initial_state=_awaiting_consent_state(),
    )
    client = _client(_make_app(graph, monkeypatch))

    body = client.get("/session/s1/events").text

    assert graph.astream_inputs == []
    assert "event: stage" not in body
