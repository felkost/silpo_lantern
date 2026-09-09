"""T11 (G9 spec): `FakeWriteBackend` serves two different carts/products/
prices, proving the extraction from
`test_write_path_interrupt_and_resume.py`'s hardcoded original is real,
not a relocation. Offline throughout.
"""

from datetime import timedelta

from langgraph.checkpoint.memory import InMemorySaver

from src.lantern.graph.state import new_recovery_state
from tests.support.write_backend import (
    FakeWriteBackend,
    WriteBackendFixture,
    build_graph,
    default_fixture,
    grant_matching_consent,
)

_SECOND_CART = {
    "id": "cart-2",
    "deliveryType": "NovaPoshta",
    "calculation": {
        "productsTotal": 10.0,
        "validations": [
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": 300},
            }
        ],
    },
    "shipments": [
        {
            "id": "ship-2",
            "companyId": "c2",
            "branchId": "b2",
            "products": [
                {"productId": "p9", "name": "Хліб", "quantity": 1, "price": 10.0}
            ],
        }
    ],
    "address": {"latitude": 49.0, "longitude": 28.0},
    "timeslot": {
        "start": "2026-09-08T10:00:00+00:00",
        "end": "2026-09-08T12:00:00+00:00",
    },
}

_SECOND_FIND_PRODUCTS = {
    "queries": [
        {
            "query": "Кава розчинна",
            "products": [
                {
                    "id": "99999999-9999-9999-9999-999999999999",
                    "name": "Кава розчинна",
                    "slug": "kava-rozchynna",
                    "price": 199.99,
                    "stock": 40,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": "22222222-2222-2222-2222-222222222222",
                    "branchId": "33333333-3333-3333-3333-333333333333",
                    "externalProductId": 111222,
                }
            ],
        }
    ]
}


def _run_one_round(backend: FakeWriteBackend):
    saver = InMemorySaver()
    graph = build_graph(backend, checkpointer=saver)
    config = {"configurable": {"thread_id": f"t-{id(backend)}"}}
    initial_state = new_recovery_state(
        session_id="s1",
        trace_id="tr1",
        now=backend.fixture.now,
        owner="owner-1",
    )
    paused = graph.invoke(initial_state, config)
    proposal = paused["candidates"][0]
    grant_matching_consent(backend, proposal)
    graph.update_state(
        config,
        {
            "consent_action_id": proposal.action_id,
            "deadline": backend.fixture.now + timedelta(seconds=90),
        },
    )
    final = graph.invoke(None, config)
    return proposal, final


def test_default_fixture_reproduces_the_known_baseline_cart() -> None:
    backend = FakeWriteBackend(default_fixture())
    proposal, final = _run_one_round(backend)

    assert proposal.product_name == "Молоко «Галичина» 2,5%"
    assert backend.write_calls, "no write happened for the default fixture"


def test_a_second_distinct_fixture_drives_a_different_cart_and_product() -> None:
    second_fixture = WriteBackendFixture(
        raw_cart=_SECOND_CART,
        find_products_response=_SECOND_FIND_PRODUCTS,
        product_name="Кава розчинна",
        product_price=199.99,
        search_terms=("Кава розчинна",),
    )
    backend = FakeWriteBackend(second_fixture)
    proposal, final = _run_one_round(backend)

    assert proposal.product_name == "Кава розчинна"
    assert backend.write_calls
    written_tool, written_args = backend.write_calls[0]
    assert written_args["shoppingCartId"] == "cart-2"


def test_the_two_fixtures_produce_genuinely_different_receipts() -> None:
    """Not just different inputs -- different OUTCOMES, proving the
    backend isn't secretly falling back to one shared cart under the
    hood."""
    first = FakeWriteBackend(default_fixture())
    _run_one_round(first)

    second_fixture = WriteBackendFixture(
        raw_cart=_SECOND_CART,
        find_products_response=_SECOND_FIND_PRODUCTS,
        product_name="Кава розчинна",
        product_price=199.99,
        search_terms=("Кава розчинна",),
    )
    second = FakeWriteBackend(second_fixture)
    _run_one_round(second)

    assert first.receipts and second.receipts
    first_receipt = first.receipts[0]
    second_receipt = second.receipts[0]
    assert first_receipt.after_state != second_receipt.after_state
