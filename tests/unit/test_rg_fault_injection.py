"""the fault-injection cases RG-01, RG-02, RG-04 and RG-05
name. Written rather than relabelled: the brief's own rule is
that a new test's status before it runs is `not_run`, never `pass`, and
the initial review found five RG rows had been claimed on the strength of
topically-related tests that did not actually exercise the rubric.

RG-03 (injected instructions via a tool error and via a tool description)
has its own file, `test_rg_injected_instructions.py`.

Offline throughout: the fake write backend stands in for MCP and Postgres
together, so every fault is injected deterministically with no network.
"""

from datetime import timedelta
from typing import Any, Dict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import (
    MAX_MCP_ATTEMPTS,
    new_recovery_state,
)
from src.lantern.mcp.errors import McpTransportError
from tests.support.write_backend import (
    FakeWriteBackend,
    build_graph,
    default_fixture,
    grant_matching_consent,
)


def _run_to_pause(backend: FakeWriteBackend, thread: str):
    graph = build_graph(backend, checkpointer=InMemorySaver())
    config: Dict[str, Any] = {"configurable": {"thread_id": thread}}
    state = graph.invoke(
        new_recovery_state(
            session_id="s1",
            trace_id=thread,
            now=backend.fixture.now,
            owner="owner-1",
        ),
        config,
    )
    return graph, config, state


# --------------------------------------------------------------------
# RG-01: context truncation -- consent is never reconstructed from an
# LLM summary. An explainer that FABRICATES a consent-shaped narration
# must not authorize anything: the guard reads consent from the store,
# and an action nobody consented to stays unconsented.
# --------------------------------------------------------------------


def test_rg01_an_llm_narration_cannot_manufacture_consent() -> None:
    backend = FakeWriteBackend(default_fixture())
    graph, config, paused = _run_to_pause(backend, "rg01")

    assert paused["status"] == "awaiting_consent"
    assert backend.consents == {}, "no consent should exist yet"

    # Resume WITHOUT recording consent -- the explainer's own text (which
    # in a truncated-context run may well read like the guest agreed)
    # is not a consent record and must not be treated as one.
    final = graph.invoke(None, config)

    assert final["status"] == "aborted"
    assert "no consent_action_id set" in (final.get("error") or "")
    assert backend.write_calls == []


def test_rg01_consent_is_read_from_the_store_not_from_state() -> None:
    """Even with a `consent_action_id` present, the guard loads the
    RECORD from the store. An id alone -- the part an LLM summary could
    plausibly carry forward -- authorizes nothing."""
    backend = FakeWriteBackend(default_fixture())
    graph, config, paused = _run_to_pause(backend, "rg01b")
    proposal = paused["candidates"][0]

    # Set the id but never store the consent record itself.
    graph.update_state(
        config,
        {
            "consent_action_id": proposal.action_id,
            "deadline": backend.fixture.now + timedelta(seconds=90),
        },
    )
    final = graph.invoke(None, config)

    assert final["status"] == "aborted"
    assert "consent not found" in (final.get("error") or "")
    assert backend.write_calls == []


# --------------------------------------------------------------------
# RG-02: a timeout AFTER the remote commit. The write landed; the
# read-back never returned. The receipt must be `unverified` and the
# journal must NOT read `confirmed` -- an unreachable read-back is never
# upgraded to a success (DR-12).
# --------------------------------------------------------------------


def test_rg02_timeout_after_remote_commit_is_unverified_never_confirmed() -> None:
    backend = FakeWriteBackend(default_fixture())
    graph, config, paused = _run_to_pause(backend, "rg02")
    proposal = paused["candidates"][0]
    grant_matching_consent(backend, proposal)

    # The write itself succeeds; the read-back that follows times out.
    original_readback = backend.fetch_cart_by_id_after_write

    def timing_out_readback(cart_id: str):
        raise McpTransportError("read-back timed out after the write committed")

    # type: ignore[method-assign]
    backend.fetch_cart_by_id_after_write = timing_out_readback

    graph.update_state(
        config,
        {
            "consent_action_id": proposal.action_id,
            "deadline": backend.fixture.now + timedelta(seconds=90),
        },
    )
    final = graph.invoke(None, config)
    # type: ignore[method-assign]
    backend.fetch_cart_by_id_after_write = original_readback

    assert backend.write_calls, "the write must have been attempted"
    assert final.get("status") == "unverified"
    assert backend.receipts, "a receipt must still be recorded"
    assert backend.receipts[-1].status == "unverified"
    assert "confirmed" not in set(backend.journal.values()), (
        "a write whose read-back never returned must not leave the journal "
        "reading confirmed"
    )


# --------------------------------------------------------------------
# RG-04: refusal and truncated structured output from the planner.
# Neither may crash the graph, and neither may produce a write.
# --------------------------------------------------------------------


def test_rg04_a_refusal_cannot_be_expressed_as_an_empty_search() -> None:
    """The planner's own structured-output schema requires at least one
    search term. A refusal therefore cannot arrive as "search for
    nothing" that the graph would process as an ordinary empty result --
    it fails validation at the boundary, loudly, where a truncated or
    refused generation belongs."""
    with pytest.raises(ValidationError):
        SearchIntent(search_terms=[])


def test_rg04_a_search_that_finds_nothing_writes_nothing() -> None:
    """The other half of the rubric: a well-formed plan whose search
    returns no usable product must end without a candidate rather than
    proposing one it has no evidence for -- and must never write."""
    backend = FakeWriteBackend(default_fixture())
    fixture = backend.fixture

    from src.lantern.graph.build import build_recovery_graph
    from src.lantern.policies.loader import load_registry

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": fixture.raw_cart["id"]},
        fetch_cart_by_id=lambda cart_id: {"cart": fixture.raw_cart},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: fixture.delivery_types_response,
        fetch_time_slots=lambda b, t: fixture.time_slots_response,
        # An empty catalogue answer: the search ran and found nothing.
        fetch_find_products_batch=lambda *a, **kw: {"queries": []},
        planner_call=lambda state: SearchIntent(
            search_terms=list(fixture.search_terms)
        ),
        explainer_call=lambda p: ExplainerOutput(
            action_id=p.action_id, guest_text_uk="x"
        ),
        now=lambda: fixture.now,
        checkpointer=InMemorySaver(),
        load_consent=backend.load_consent,
        call_write_tool=backend.call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )
    final = graph.invoke(
        new_recovery_state(
            session_id="s1", trace_id="rg04b", now=fixture.now, owner="owner-1"
        ),
        {"configurable": {"thread_id": "rg04b"}},
    )

    assert backend.write_calls == []
    assert final.get("status") in ("no_action_available", "aborted")


# --------------------------------------------------------------------
# RG-05: a persistently failing / hanging MCP call. The rubric asks for
# completion within budget. Per an earlier decision the budget loop is NOT wired
# (`enforce_budget` is called nowhere, `cycles_used`/`tokens_used` are
# never incremented), so what CAN be asserted today is that a persistent
# transport failure terminates rather than looping -- and that is
# recorded honestly as such in coverage.json, not as a pass of the full
# rubric.
# --------------------------------------------------------------------


def test_rg05_a_persistent_transport_failure_terminates_rather_than_looping() -> None:
    backend = FakeWriteBackend(default_fixture())
    fixture = backend.fixture

    calls = {"n": 0}

    def always_failing_cart_read(cart_id: str):
        calls["n"] += 1
        raise McpTransportError("upstream is down")

    from src.lantern.graph.build import build_recovery_graph
    from src.lantern.policies.loader import load_registry

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": fixture.raw_cart["id"]},
        fetch_cart_by_id=always_failing_cart_read,
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: fixture.delivery_types_response,
        fetch_time_slots=lambda b, t: fixture.time_slots_response,
        fetch_find_products_batch=lambda *a, **kw: fixture.find_products_response,
        planner_call=lambda state: SearchIntent(
            search_terms=list(fixture.search_terms)
        ),
        explainer_call=lambda p: ExplainerOutput(
            action_id=p.action_id, guest_text_uk="x"
        ),
        now=lambda: fixture.now,
        checkpointer=InMemorySaver(),
        load_consent=backend.load_consent,
        call_write_tool=backend.call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )

    with pytest.raises(McpTransportError):
        graph.invoke(
            new_recovery_state(
                session_id="s1", trace_id="rg05", now=fixture.now, owner="owner-1"
            ),
            {"configurable": {"thread_id": "rg05"}},
        )

    assert backend.write_calls == [], "a failing read must never reach a write"
    assert calls["n"] < MAX_MCP_ATTEMPTS, (
        "the failure surfaced rather than retrying until the MCP attempt "
        "ceiling -- the graph terminates on a persistent transport error"
    )
