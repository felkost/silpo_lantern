"""T17: the write redactor emits no raw args, and the
write call is actually wrapped in a span.

Both halves matter and only one is obvious. The redactor is easy to write
and easy to leave unwired: before this test the write was the one step in
the whole graph that emitted no trace at all -- `traced_llm_call` wrapped
the planner and the explainer, and the single call that changes a guest's
cart went out unobserved. That was found by an audit after the live runs
had already happened, not by the suite.

Redaction is exercised as a plain function, never by enabling tracing:
`tracer.py`'s own module docstring records that `LANGSMITH_TRACING=true`
attempts a real outbound POST even with a bogus key.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from src.lantern.graph.build import build_recovery_graph
from src.lantern.observability.tracer import (
    redact_write_input,
    redact_write_output,
)
from src.lantern.policies.loader import load_registry

_REAL_CART_ID = "4e83e418-a6b1-4187-b961-f8c9fb4ba2f5"
_REAL_PRODUCT_ID = "1ed3b23b-68d2-62b0-9c49-19831a0576fe"
_REAL_COMPANY_ID = "1ec88c5d-a050-669c-8467-570a157f3e31"
_REAL_BRANCH_ID = "1ee7fab3-7713-6a0c-b802-8d149aac137a"

_WRITE_ARGS: Dict[str, Any] = {
    "shoppingCartId": _REAL_CART_ID,
    "products": [
        {
            "productId": _REAL_PRODUCT_ID,
            "companyId": _REAL_COMPANY_ID,
            "branchId": _REAL_BRANCH_ID,
            "quantity": 3,
            "addQuantity": False,
        }
    ],
}


def test_t17_no_identifier_from_the_write_args_reaches_the_trace() -> None:
    """The cart id and the product id identify a real person's real
    basket. A third-party trace is exactly where they must not appear."""
    traced = redact_write_input(
        {"tool_name": "silpo_add_or_update_cart_products", "args": _WRITE_ARGS}
    )

    rendered = repr(traced)
    for identifier in (
        _REAL_CART_ID,
        _REAL_PRODUCT_ID,
        _REAL_COMPANY_ID,
        _REAL_BRANCH_ID,
    ):
        assert identifier not in rendered, f"{identifier} reached the trace"

    # What a reviewer does need: that a write happened, against which tool,
    # how many lines and at what quantity.
    assert traced["tool_name"] == "silpo_add_or_update_cart_products"
    assert traced["product_count"] == 1
    assert traced["quantities"] == [3]
    assert traced["add_quantity"] == [False]


def test_an_unrecognised_argument_shape_is_not_traced_verbatim() -> None:
    """The two LLM redactors fall back to `dict(kwargs)` because their
    inputs carry nothing worth hiding. This one must not: a shape it does
    not recognise is the case where leaking everything is most likely."""
    traced = redact_write_input({"tool_name": "something_new", "args": _REAL_CART_ID})

    assert _REAL_CART_ID not in repr(traced)


def test_the_write_callable_reaching_the_node_is_wrapped_in_a_span() -> None:
    """The redactor above is worth nothing if nothing calls it. Builds the
    real graph and checks the callable it hands the write node is not the
    one that went in -- i.e. that it passed through `traced_llm_call`.
    """
    seen: List[Tuple[str, Dict[str, Any]]] = []

    def bare_write(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        seen.append((tool_name, args))
        return {"success": True, "summary": "", "products": []}

    graph = build_recovery_graph(
        fetch_my_cart=lambda: {},
        fetch_cart_by_id=lambda cart_id: {},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: {},
        fetch_time_slots=lambda branch_id, types: {},
        fetch_find_products_batch=lambda *args, **kwargs: {},
        planner_call=lambda state: None,
        explainer_call=lambda proposal: None,
        now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        call_write_tool=bare_write,
    )

    node = graph.nodes["write_and_readback"]
    wrapped = node.bound.func.__closure__  # type: ignore[union-attr]
    injected = [
        cell.cell_contents
        for cell in (wrapped or ())
        if callable(cell.cell_contents) and cell.cell_contents is not bare_write
    ]
    assert injected, "the write node closed over no callable at all"
    assert bare_write not in [
        cell.cell_contents for cell in (wrapped or ())
    ], "the raw write callable reached the node — it was never wrapped in a span"


def test_t17_the_write_response_does_not_leak_the_product_id_either() -> None:
    """Found live, after `redact_write_input` was already in place: the
    span's inputs were clean and its outputs carried the real product id
    verbatim, because the tool echoes it back and only inputs were being
    redacted. Redacting one side of a call is not redacting the call.
    """
    response = {
        "success": True,
        "summary": "Updated 1 product(s)",
        "products": [{"productId": _REAL_PRODUCT_ID, "quantity": 2}],
    }

    traced = redact_write_output(response)

    assert _REAL_PRODUCT_ID not in repr(traced)
    assert traced["success"] is True
    assert traced["summary"] == "Updated 1 product(s)"
    assert traced["product_count"] == 1
    assert traced["quantities"] == [2]


def test_an_unrecognised_write_response_is_not_traced_verbatim() -> None:
    assert _REAL_PRODUCT_ID not in repr(redact_write_output(_REAL_PRODUCT_ID))
