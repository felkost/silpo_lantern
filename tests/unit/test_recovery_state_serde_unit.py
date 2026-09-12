"""`RecoveryState` round-trips through
LangGraph's own serializer directly — no live Postgres, so this lives in
`tests/unit/` and runs inside `make gate`. The full checkpointer round-trip
(`get_checkpointer` against real Neon) is a SEPARATE test in
`tests/integration/`, outside the gate, per the project's existing
convention (`Makefile`'s own comment on `test-integration`).

A real, measured finding drove this module's actual content, not merely its
existence: `langgraph.checkpoint.base.BaseCheckpointSaver`'s default serde
IS `JsonPlusSerializer` (confirmed directly — `BaseCheckpointSaver.serde` at
the class level), and round-tripping a `RecoveryState` carrying real domain
Pydantic models (`ActionProposal`, `EvidenceTuple`) through it WORKS today
but logs (via Python's `logging`, NOT `warnings.warn` — confirmed by reading
`jsonplus.py`'s own source, not assumed): "Deserializing unregistered type
... This will be blocked in a future version." Silently ignoring it would
mean a future `langgraph` upgrade breaks this project's own checkpointing
with no local signal ever having been acted on.

Second finding, also from reading the source rather than assuming: the
warning is deduplicated in a process-global module-level set
(`_warned_unregistered_types`), keyed by (module, classname) — a second
call for the same type in the same process never logs again. The negative
control below resets that set explicitly, so its result does not depend on
whatever other tests happened to run first in this same pytest process
(this project also runs `pytest-randomly` — collection order is not fixed).
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import ActionProposal, EvidenceTuple, Receipt
from src.lantern.graph.state import new_recovery_state, recovery_state_serde


def _now() -> datetime:
    return datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _proposal_with_evidence() -> ActionProposal:
    evidence = EvidenceTuple(
        product_id="795319",
        price=Decimal("39.99"),
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=_now(),
    )
    return ActionProposal(
        action_id="a1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Молоко «Галичина» 2,5%",
        quantity=Decimal("1"),
        expected_delta=Decimal("39.99"),
        canonical_args={"productId": "795319", "quantity": 1, "addQuantity": False},
        evidence=[evidence],
    )


def test_a_fresh_state_round_trips_byte_identical() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    serde = recovery_state_serde()

    encoded = serde.dumps_typed(state)
    decoded = serde.loads_typed(encoded)

    assert decoded == state


def test_a_state_with_populated_domain_models_round_trips_without_warning(
    caplog,
) -> None:
    """Reproduces the exact defect this test module exists to catch: without
    registering domain models in `allowed_msgpack_modules`, this same
    round-trip logs a live deprecation warning instead of working cleanly.
    """
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["candidates"] = [_proposal_with_evidence()]

    serde = recovery_state_serde()

    with caplog.at_level("WARNING"):
        encoded = serde.dumps_typed(state)
        decoded = serde.loads_typed(encoded)

    assert not any("unregistered type" in record.message for record in caplog.records)
    assert decoded == state
    assert isinstance(decoded["candidates"][0], ActionProposal)
    assert decoded["candidates"][0].evidence[0].price == Decimal("39.99")


def _compensation_proposal() -> ActionProposal:
    """T22: the production serializer must round-trip the
    two fields the undo added (`kind`, `compensates_action_id`) and a NEGATIVE
    `Decimal` quantity/delta cleanly -- probed once in the session that
    produced the stage spec (M3); pinned here as a repeatable test rather
    than left as a claim only that session could re-derive.
    """
    evidence = EvidenceTuple(
        product_id="p1",
        price=Decimal("86.84"),
        availability=True,
        source_tool="silpo_get_shopping_cart_by_id",
        captured_at=_now(),
    )
    return ActionProposal(
        action_id="comp-1",
        tool_name="silpo_remove_cart_products",
        product_name="Товар",
        quantity=Decimal("-1"),
        expected_delta=Decimal("-86.84"),
        canonical_args={"shoppingCartId": "cart-1", "products": [{"productId": "p1"}]},
        evidence=[evidence],
        kind="compensate",
        compensates_action_id="orig-1",
    )


def test_a_compensation_proposal_and_compensable_receipts_round_trip() -> None:
    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["candidates"] = [_compensation_proposal()]
    state["compensable"] = [
        Receipt(
            action_id="orig-1",
            session_id="s1",
            owner="owner-1",
            before_state={
                "cart_id": "cart-1",
                "products_total": "500.77",
                "products": [],
            },
            after_state={
                "cart_id": "cart-1",
                "products_total": "587.61",
                "products": [
                    {
                        "product_id": "p1",
                        "name": "Товар",
                        "quantity": "1",
                        "price": "86.84",
                    }
                ],
            },
            verified=True,
            status="receipt",
            reason="",
            expected_delta=Decimal("86.84"),
            actual_delta=Decimal("86.84"),
            created_at=_now(),
            blocker_cleared=False,
            kind="add",
        )
    ]

    serde = recovery_state_serde()
    decoded = serde.loads_typed(serde.dumps_typed(state))

    assert decoded == state
    assert decoded["candidates"][0].kind == "compensate"
    assert decoded["candidates"][0].quantity == Decimal("-1")
    assert decoded["candidates"][0].expected_delta == Decimal("-86.84")
    assert decoded["compensable"][0].action_id == "orig-1"


def test_default_serializer_would_have_warned_without_the_allowlist(caplog) -> None:
    """Negative control: proves the previous test's clean result comes from
    `recovery_state_serde`'s allowlist, not from `ActionProposal` being
    msgpack-safe on its own. Resets the SDK's own process-global dedup set
    first (see module docstring) so this assertion holds regardless of test
    execution order.
    """
    from langgraph.checkpoint.serde import jsonplus

    jsonplus._warned_unregistered_types.clear()

    state = new_recovery_state(session_id="s1", trace_id="t1", now=_now())
    state["candidates"] = [_proposal_with_evidence()]

    unregistered_serde = jsonplus.JsonPlusSerializer()
    encoded = unregistered_serde.dumps_typed(state)

    with caplog.at_level("WARNING"):
        unregistered_serde.loads_typed(encoded)

    assert any("unregistered type" in record.message for record in caplog.records)
