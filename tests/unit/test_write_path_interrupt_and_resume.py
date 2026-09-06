"""T14/T15/T15b (G5+G6 stage spec): the compiled graph pauses at
`write_guard` under a real checkpointer, resumes correctly from a FRESH
graph object using only what a real API process would have (the consent
recorded in "Neon" -- here a fake dict, never the interrupt's own resume
payload), and a crash after the write's own side effect reconciles on the
next resume instead of writing twice.

Offline throughout: `langgraph.checkpoint.memory.InMemorySaver` stands in
for the Neon-backed `AsyncPostgresSaver` this project uses in production —
measured (kickoff probe) to expose the same pause/resume contract for a
sync graph. No live MCP or LLM call.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from langgraph.checkpoint.memory import InMemorySaver

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ConsentRecord
from src.lantern.domain.normalizer import normalize_cart
from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.policies.loader import load_registry

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
_TOOL_HASH = "reviewed-hash-abc"

_RAW_CART: Dict[str, Any] = {
    "id": "cart-1",
    "deliveryType": "NovaPoshta",
    "calculation": {
        "productsTotal": 35.0,  # matches the one line item below (35.0 * 1)
        "validations": [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 599},
            }
        ],
    },
    "shipments": [
        {
            "id": "ship-1",
            "companyId": "c1",
            "branchId": "b1",
            "products": [
                {
                    "productId": "p1",
                    "name": "Молоко «Галичина» 2,5%",
                    "quantity": 1,
                    "price": 35.0,
                }
            ],
        }
    ],
    "address": {"latitude": 50.45, "longitude": 30.52},
    "timeslot": {
        "start": "2026-09-08T10:00:00+00:00",
        "end": "2026-09-08T12:00:00+00:00",
    },
}

_FIND_PRODUCTS_RESPONSE = {
    "queries": [
        {
            "query": "Молоко «Галичина» 2,5%",
            "products": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "stock": 600,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": "22222222-2222-2222-2222-222222222222",
                    "branchId": "33333333-3333-3333-3333-333333333333",
                    "externalProductId": 795319,
                }
            ],
        }
    ]
}

_TIME_SLOTS_RESPONSE = {
    "slots": [
        {
            "start": "2026-09-08T10:00:00Z",
            "end": "2026-09-08T12:00:00Z",
            "available": True,
            "deliveryType": "SelfPickup",
            "deliveryCost": 0,
            "deliveryCostMap": [],
            "minOrderCost": 199,
        }
    ]
}

_DELIVERY_TYPES_RESPONSE: Dict[str, Any] = {
    "success": True,
    "summary": "",
    "options": [],
}


def _fake_planner(state: Any) -> SearchIntent:
    return SearchIntent(search_terms=["Молоко «Галичина» 2,5%"], quantity_hint=1)


def _fake_explainer(proposal: Any) -> ExplainerOutput:
    return ExplainerOutput(action_id=proposal.action_id, guest_text_uk="Додати товар")


class _FakeWriteBackend:
    """Stands in for `memory.repository` + `mcp.session` together —
    everything the write path needs, backed by plain dicts so the test
    can inspect exactly what happened."""

    def __init__(self) -> None:
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[tuple, str] = {}
        self.receipts: list = []
        self.write_calls: list = []
        self.write_side_effect_applied = False
        self.cart_after_write = dict(_RAW_CART)
        self.crash_readback_once = False
        self._readback_crashed_already = False

    def load_consent(self, action_id: str):
        record = self.consents.get(action_id)
        if record is None:
            return None, True
        return record, record.expires_at <= _NOW

    def claim_and_consume(
        self, owner: str, cart_id: str, action_id: str, args_hash: str
    ):
        key = (owner, cart_id, action_id)
        if key in self.journal:
            return False, self.journal[key]
        consent = self.consents[action_id]
        consent_object = consent.model_copy(update={"consumed_at": _NOW})
        self.consents[action_id] = consent_object
        self.journal[key] = "in_flight"
        return True, "in_flight"

    def mark_action(self, owner: str, cart_id: str, action_id: str, state: str) -> None:
        self.journal[(owner, cart_id, action_id)] = state

    def save_receipt(self, receipt: Any) -> None:
        self.receipts.append(receipt)

    def tool_schema_hashes(self, tool_name: str):
        return (_TOOL_HASH, _TOOL_HASH, False)

    def call_write_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.write_calls.append((tool_name, args))
        self.write_side_effect_applied = True
        product = args["products"][0]
        # Apply the write: the new product is a DIFFERENT id from the
        # cart's existing "p1" line item, so this is an ADD, not a
        # replace of the same line -- the existing line stays, matching
        # what a real server does for a genuinely new product.
        existing_products = _RAW_CART["shipments"][0]["products"]
        existing_total = sum(p["price"] * p["quantity"] for p in existing_products)
        new_line_total = 39.99 * product["quantity"]
        self.cart_after_write = {
            **_RAW_CART,
            "calculation": {
                **_RAW_CART["calculation"],
                # round() to avoid a float-precision artifact (74.99000000000001)
                # that would make canonical_diff's own invariant check fail —
                # a test-fixture concern, since production code sums via
                # `Decimal(str(...))` throughout, never raw floats.
                "productsTotal": round(existing_total + new_line_total, 2),
            },
            "shipments": [
                {
                    **_RAW_CART["shipments"][0],
                    "products": [
                        *existing_products,
                        {
                            "productId": product["productId"],
                            "name": "Молоко «Галичина» 2,5%",
                            "quantity": product["quantity"],
                            "price": 39.99,
                        },
                    ],
                }
            ],
        }
        return {"success": True, "summary": "ok", "products": [product]}

    def fetch_cart_by_id_after_write(self, cart_id: str) -> Dict[str, Any]:
        # T15b: simulate a process kill between the write's own side
        # effect (already applied above, permanently, before this is
        # even called) and the read-back completing -- exactly the
        # window RG-07 names. A plain `RuntimeError` is deliberately NOT
        # one of the exception types the node's read-back `except` clause
        # catches, so it propagates out of the node and `graph.invoke`
        # itself raises, leaving no checkpoint past `write_guard`.
        if self.crash_readback_once and not self._readback_crashed_already:
            self._readback_crashed_already = True
            raise RuntimeError("simulated process kill before read-back completes")
        return {"cart": self.cart_after_write}


def _build_graph(backend: _FakeWriteBackend, checkpointer: Any = None):
    return build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": "cart-1"},
        fetch_cart_by_id=lambda cart_id: (
            backend.fetch_cart_by_id_after_write(cart_id)
            if backend.write_side_effect_applied
            else {"cart": _RAW_CART}
        ),
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        fetch_find_products_batch=lambda *a, **kw: _FIND_PRODUCTS_RESPONSE,
        planner_call=_fake_planner,
        explainer_call=_fake_explainer,
        now=lambda: _NOW,
        checkpointer=checkpointer,
        load_consent=backend.load_consent,
        call_write_tool=backend.call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )


def _grant_matching_consent(backend: _FakeWriteBackend, proposal: Any) -> None:
    cart = normalize_cart(_RAW_CART)
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-1",
        cart_id="cart-1",
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
    backend.consents[proposal.action_id] = consent


def test_t14_graph_pauses_before_write_guard() -> None:
    backend = _FakeWriteBackend()
    saver = InMemorySaver()
    graph = _build_graph(backend, checkpointer=saver)
    config = {"configurable": {"thread_id": "t1"}}

    from src.lantern.graph.state import new_recovery_state

    initial_state = new_recovery_state(
        session_id="s1", trace_id="tr1", now=_NOW, owner="owner-1"
    )
    paused_state = graph.invoke(initial_state, config)

    assert paused_state["status"] == "awaiting_consent"
    assert len(paused_state["candidates"]) == 1
    assert graph.get_state(config).next == ("write_guard",)
    assert backend.write_calls == []


def test_t15_resume_from_a_fresh_process_reads_consent_from_neon() -> None:
    backend = _FakeWriteBackend()
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "t2"}}

    from src.lantern.graph.state import new_recovery_state

    graph = _build_graph(backend, checkpointer=saver)
    initial_state = new_recovery_state(
        session_id="s1", trace_id="tr1", now=_NOW, owner="owner-1"
    )
    paused_state = graph.invoke(initial_state, config)
    proposal = paused_state["candidates"][0]
    _grant_matching_consent(backend, proposal)

    # A FRESH graph object -- resume never trusts the process that paused.
    fresh_graph = _build_graph(backend, checkpointer=saver)
    fresh_graph.update_state(config, {"consent_action_id": proposal.action_id})
    final_state = fresh_graph.invoke(None, config)

    assert final_state["status"] == "verified"
    assert final_state["receipt"] is not None
    assert final_state["receipt"].status == "receipt"
    assert len(backend.write_calls) == 1


def test_t15b_crash_after_write_before_readback_reconciles_on_resume() -> None:
    """Simulates a process kill right after the write's own side effect
    but before the read-back completes -- `write_and_readback_node` is
    the node LangGraph re-runs on resume (measured: `interrupt_before`
    does not protect it), so its own `claim_and_consume` call is what must
    prevent a second write, not the guard before it (D-G5-07b/07c)."""
    backend = _FakeWriteBackend()
    backend.crash_readback_once = True
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "t3"}}

    from src.lantern.graph.state import new_recovery_state

    graph = _build_graph(backend, checkpointer=saver)
    initial_state = new_recovery_state(
        session_id="s1", trace_id="tr1", now=_NOW, owner="owner-1"
    )
    paused_state = graph.invoke(initial_state, config)
    proposal = paused_state["candidates"][0]
    _grant_matching_consent(backend, proposal)
    graph.update_state(config, {"consent_action_id": proposal.action_id})

    # First resume: the write happens for real (backend.write_calls grows
    # by one, permanently), but the simulated read-back crash raises
    # before `write_and_readback_node` returns -- no checkpoint advances
    # past `write_guard`, and `mark_action` never ran.
    try:
        graph.invoke(None, config)
        raise AssertionError("expected the simulated read-back crash to propagate")
    except RuntimeError:
        pass

    assert len(backend.write_calls) == 1
    assert backend.journal[("owner-1", "cart-1", proposal.action_id)] == "in_flight"

    # Resume from a FRESH graph object, as a real restarted process would.
    # `claim_and_consume` sees the row already exists -> reconciles from
    # a read-back only, never writes a second time.
    fresh_graph = _build_graph(backend, checkpointer=saver)
    final_state = fresh_graph.invoke(None, config)

    assert len(backend.write_calls) == 1  # still exactly one write, ever
    assert final_state["status"] == "verified"
    assert final_state["receipt"].status == "receipt"
    assert backend.journal[("owner-1", "cart-1", proposal.action_id)] == "confirmed"


def test_the_consent_pause_does_consume_an_absolute_deadline() -> None:
    """`new_recovery_state` used to claim the consent wait was excluded
    from the budget "by construction", because the pause runs no node. It
    is not: `deadline` is an absolute timestamp, and wall-clock time passes
    whether or not code executes. Pinned because that false claim reached
    production and refused a real write with "insufficient budget reserve"
    after a guest simply took a couple of minutes to decide.

    Only a duration-accumulating budget would have the claimed property;
    the fix is re-basing the deadline when consent is recorded, which
    `apps/api/routes.py` does.
    """
    from src.lantern.graph.state import (
        ACTIVE_EXECUTION_SECONDS,
        has_write_reserve,
        new_recovery_state,
    )

    started = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    state = new_recovery_state(session_id="s1", trace_id="t1", now=started)

    # Immediately after the read pipeline: the write reserve is available.
    assert has_write_reserve(state, started + timedelta(seconds=5)) is True

    # The guest reads three proposals and thinks. No node has run in the
    # meantime -- and the reserve is gone anyway.
    deliberated = started + timedelta(seconds=ACTIVE_EXECUTION_SECONDS + 1)
    assert has_write_reserve(state, deliberated) is False

    # Re-basing the deadline, as recording consent does, restores it.
    rebased = {
        **state,
        "deadline": deliberated + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
    }
    assert has_write_reserve(rebased, deliberated) is True
