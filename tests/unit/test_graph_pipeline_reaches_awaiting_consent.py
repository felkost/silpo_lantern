"""End-to-end offline proof: the full
read -> diagnose -> compare_channels -> plan -> collect_and_gate -> rank ->
explain pipeline, wired exactly as `build_recovery_graph` assembles it in
production, reaches `awaiting_consent` with a real `ActionProposal` —
using FAKE MCP/LLM callables, no live network or LLM call. Proves the
wiring itself (call ordering, state merging, fail-safe short-circuiting) is
correct, independent of any live smoke test.
"""

import json
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
                    # G5+G6 (D-G5-03): `id`/`companyId`/`branchId` are the
                    # write tool's own argument fields — required here
                    # since the offline fixture went end-to-end.
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
    # The gap is 599 - 404.89 = 194.11, and one unit is 39.99, so the
    # pipeline proposes the five units that actually close it -- not the
    # single unit the planner's own `quantity_hint` used to dictate.
    assert proposal.quantity == Decimal("5")
    assert proposal.expected_delta == Decimal("199.95")
    assert proposal.guest_text_uk != ""
    assert proposal.canonical_args == {
        "shoppingCartId": "cart-1",
        "products": [
            {
                "productId": "11111111-1111-1111-1111-111111111111",
                "companyId": "22222222-2222-2222-2222-222222222222",
                "branchId": "33333333-3333-3333-3333-333333333333",
                "quantity": 5,
                "addQuantity": False,
            }
        ],
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


# The two blockers the author's real cart actually carried on the first
# live run: a delivery slot that disappeared and a line item whose stock
# fell to zero. Neither is a cost gap, and neither can be cleared by adding
# products -- which is the only kind of proposal this pipeline can build.
_NON_COST_BLOCKERS = [
    {"level": "error", "type": "timeslot", "message": "timeslot.not_available"},
    {
        "level": "error",
        "type": "product",
        "message": "product.offer.stock.max",
        "context": {"productId": "p1", "stock": 0},
    },
]


def _cart_without_a_cost_gap() -> dict:
    cart = json.loads(json.dumps(_RAW_CART))
    # Well above any minimum, so no order.cost.min validation exists.
    cart["calculation"]["productsTotal"] = 1279.19
    cart["calculation"]["validations"] = _NON_COST_BLOCKERS
    return cart


def test_a_cart_with_no_cost_gap_never_reaches_the_planner() -> None:
    """Measured on the first live run: this exact cart reached the planner,
    which invented three drinks costing 18-26 UAH. Adding them could not
    have cleared a missing timeslot or an out-of-stock line, and the write
    path would have executed one and issued a `verified` receipt for it --
    verified against the expected delta, which says nothing about whether
    the cart became orderable.
    """
    planner_calls: list[int] = []

    def counting_planner(state: RecoveryState) -> SearchIntent:
        planner_calls.append(1)
        return SearchIntent(search_terms=["x"])

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": "cart-1"},
        fetch_cart_by_id=lambda cart_id: {"cart": _cart_without_a_cost_gap()},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        fetch_find_products_batch=lambda *a, **kw: _FIND_PRODUCTS_RESPONSE,
        planner_call=counting_planner,
        explainer_call=_fake_explainer,
        now=lambda: _NOW,
    )

    final_state = graph.invoke(
        new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    )

    assert final_state["status"] == "no_action_available"
    assert planner_calls == [], "the planner costs money and had nothing to plan"
    assert final_state["candidates"] == []
    # The diagnosis is still produced: the guest is told what blocks the
    # cart even when this system has no action to offer for it.
    assert final_state["diagnosis"] is not None
    assert len(final_state["diagnosis"].blockers) == 2


def test_an_empty_candidate_list_never_asks_for_consent() -> None:
    """A gap can exist and still leave nothing to offer -- the Evidence Gate
    drops candidates missing write identity, over stock, or off the weighted
    step. `awaiting_consent` with an empty list asks the guest to approve
    nothing, and the API emitted `consent_required` for exactly that.
    """
    explainer_calls: list[int] = []

    def counting_explainer(proposal) -> ExplainerOutput:
        explainer_calls.append(1)
        return _fake_explainer(proposal)

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": "cart-1"},
        fetch_cart_by_id=lambda cart_id: {"cart": _RAW_CART},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        # The search returns nothing the gate can accept.
        fetch_find_products_batch=lambda *a, **kw: {"queries": []},
        planner_call=_fake_planner,
        explainer_call=counting_explainer,
        now=lambda: _NOW,
    )

    final_state = graph.invoke(
        new_recovery_state(session_id="s1", trace_id="t1", now=_NOW)
    )

    assert final_state["status"] == "no_action_available"
    assert final_state["status"] != "awaiting_consent"
    assert explainer_calls == []
