"""End-to-end offline proof: the full
read -> diagnose -> compare_channels -> plan -> collect_and_gate -> rank ->
explain pipeline, wired exactly as `build_recovery_graph` assembles it in
production, reaches `awaiting_consent` with a real `ActionProposal` —
using FAKE MCP/LLM callables, no live network or LLM call. Proves the
wiring itself (call ordering, state merging, fail-safe short-circuiting) is
correct, independent of any live smoke test.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState, new_recovery_state
from src.lantern.policies.loader import load_registry

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

# Shape measured against `normalize_cart`'s own documented input contract
# and the tracked live-cart fixture's field names — not invented.
_RAW_CART = {
    "id": "cart-1",
    "deliveryType": "NovaPoshta",
    "calculation": {
        "productsTotal": 404.89,
        "total": 533.89,
        "totalAfterDiscounts": 488.96,
        "subTotal": 812.39,
        "delivery": {"total": 129},
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
                    "name": "Молоко «Галичина» 2,5%",
                    "slug": "moloko-halychyna",
                    "price": 39.99,
                    "available": True,
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

_DELIVERY_TYPES_RESPONSE = {
    "success": True,
    "summary": "",
    "options": [{"deliveryType": "SelfPickup", "branchId": "b2", "description": "x"}],
}


def _fake_planner(state: RecoveryState) -> SearchIntent:
    assert state["diagnosis"] is not None  # planner runs only after diagnose
    return SearchIntent(search_terms=["Молоко «Галичина» 2,5%"], quantity_hint=1)


def _fake_explainer(proposal) -> ExplainerOutput:
    return ExplainerOutput(
        action_id=proposal.action_id,
        guest_text_uk="Додайте молоко «Галичина» — це додасть 39,99 ₴ до суми кошика.",
    )


def _build_graph():
    return build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": "cart-1"},
        fetch_cart_by_id=lambda cart_id: {"cart": _RAW_CART},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        fetch_find_products_batch=lambda *a, **kw: _FIND_PRODUCTS_RESPONSE,
        planner_call=_fake_planner,
        explainer_call=_fake_explainer,
        now=lambda: _NOW,
    )


def test_pipeline_reaches_awaiting_consent_with_a_real_candidate() -> None:
    graph = _build_graph()
    initial_state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)

    final_state = graph.invoke(initial_state)

    assert final_state["status"] == "awaiting_consent"
    assert final_state["cart"] is not None
    assert final_state["diagnosis"] is not None
    assert final_state["diagnosis"].primary_code == "order.cost.min"
    assert len(final_state["candidates"]) == 1

    proposal = final_state["candidates"][0]
    assert proposal.product_name == "Молоко «Галичина» 2,5%"
    assert proposal.expected_delta == Decimal("39.99")
    assert proposal.guest_text_uk != ""
    assert proposal.canonical_args == {
        "productId": "795319",
        "quantity": 1,
        "addQuantity": False,
    }


def test_pipeline_produces_a_channel_comparison_alongside_the_candidate() -> None:
    graph = _build_graph()
    initial_state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)

    final_state = graph.invoke(initial_state)

    assert len(final_state["channel_comparison"]) == 1
    row = final_state["channel_comparison"][0]
    assert row.snapshot.delivery_type == "SelfPickup"


def test_a_cart_shape_error_in_read_aborts_before_any_llm_call() -> None:
    planner_calls = []

    def counting_planner(state: RecoveryState) -> SearchIntent:
        planner_calls.append(1)
        return SearchIntent(search_terms=["x"])

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": "cart-1"},
        fetch_cart_by_id=lambda cart_id: {
            "cart": {"calculation": {}}
        },  # no productsTotal
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        fetch_find_products_batch=lambda *a, **kw: _FIND_PRODUCTS_RESPONSE,
        planner_call=counting_planner,
        explainer_call=_fake_explainer,
        now=lambda: _NOW,
    )
    initial_state = new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)

    final_state = graph.invoke(initial_state)

    assert final_state["status"] == "aborted"
    assert "productsTotal" in final_state["error"]
    assert planner_calls == []  # the LLM is never reached after an abort
