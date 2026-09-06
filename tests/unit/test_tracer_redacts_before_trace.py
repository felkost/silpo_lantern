"""Redaction happens via `langsmith.traceable`'s own `process_inputs`/
`process_outputs` hooks. Two real, measured findings about the SDK,
neither assumed:

1. These hooks are called ONLY when tracing is actually active
   (`LANGSMITH_TRACING=true` + a valid-looking API key) — probed directly:
   `process_inputs` is never invoked with no env vars set. This project's
   offline gate never sets those variables, so this test suite tests the
   REDACTION FUNCTIONS directly, as plain functions — never by enabling
   live tracing, which would attempt a real outbound HTTPS call (also
   probed directly: a bogus key still produces a live POST to
   api.smith.langchain.com, rejected with 403 — not a local no-op).
2. `process_inputs` receives a dict keyed by parameter name
   (`{"state": <value>}` for a one-positional-arg function) — probed
   directly against the installed SDK, not assumed from documentation.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import ActionProposal, EvidenceTuple
from src.lantern.graph.state import new_recovery_state
from src.lantern.observability.tracer import (
    redact_explainer_input,
    redact_planner_input,
)


def test_redact_planner_input_excludes_cart_coordinates() -> None:
    """Address/coordinate-adjacent
    data does not belong in a third-party trace, even when the third
    party (LangSmith) is a trusted vendor — traces reach a system outside
    our own infrastructure, regardless of which vendor."""
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )
    traced = redact_planner_input({"state": state})

    assert "latitude" not in str(traced)
    assert "longitude" not in str(traced)
    assert traced["session_id"] == "s1"
    assert traced["trace_id"] == "t1"


def test_redact_planner_input_summarizes_diagnosis_not_the_full_cart() -> None:
    from src.lantern.domain.diagnosis import diagnose
    from src.lantern.policies.loader import load_registry
    from src.lantern.domain.normalizer import normalize_cart

    raw_cart = {
        "id": "cart-1",
        "calculation": {
            "productsTotal": 404.89,
            "validations": [
                {
                    "level": "error",
                    "type": "order",
                    "message": "order.cost.min",
                    "context": {"orderCostMin": 599},
                }
            ],
        },
        "address": {"latitude": 50.45, "longitude": 30.52},
    }
    cart = normalize_cart(raw_cart)
    diagnosis = diagnose(cart, load_registry())
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )
    state["cart"] = cart
    state["diagnosis"] = diagnosis

    traced = redact_planner_input({"state": state})

    assert traced["primary_code"] == "order.cost.min"
    assert traced["gap"] == "194.11"
    assert (
        "products_total" not in traced
    )  # only the gap/code summary, not raw cart data


def test_redact_planner_input_handles_no_diagnosis_yet() -> None:
    state = new_recovery_state(
        session_id="s1", trace_id="t1", now=datetime.now(timezone.utc)
    )
    traced = redact_planner_input({"state": state})
    assert traced["primary_code"] is None
    assert traced["gap"] is None


def test_redact_explainer_input_excludes_evidence_metadata() -> None:
    """Only the guest-relevant fields — never `source_tool`/`captured_at`,
    which are audit-only and add nothing a trace reviewer needs repeated."""
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

    traced = redact_explainer_input({"proposal": proposal})

    assert traced == {
        "action_id": "a1",
        "product_name": "Молоко",
        "quantity": "1",
        "expected_delta": "39.99",
    }
    assert "source_tool" not in str(traced)
