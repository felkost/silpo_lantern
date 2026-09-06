"""The full checkpointer round-trip against real Neon, with
`RecoveryState`'s own allowlisted serde (`recovery_state_serde`,
`src/lantern/graph/state.py`) — not the SDK default, which the unit-level
test in `tests/unit/test_recovery_state_serde_unit.py` proves logs a
deprecation warning for this project's own domain models. Needs a live
Postgres, so it lives here, outside the gate, per this project's existing
convention.
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.domain.models import ActionProposal, EvidenceTuple
from src.lantern.graph.state import new_recovery_state, recovery_state_serde
from src.lantern.memory.checkpointer import get_checkpointer

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


@pytest.mark.asyncio
async def test_recovery_state_round_trips_through_a_real_checkpointer() -> None:
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    now = datetime.now(timezone.utc)

    evidence = EvidenceTuple(
        product_id="795319",
        price=Decimal("39.99"),
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=now,
    )
    proposal = ActionProposal(
        action_id="a1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Молоко «Галичина» 2,5%",
        quantity=Decimal("1"),
        expected_delta=Decimal("39.99"),
        canonical_args={"productId": "795319", "quantity": 1, "addQuantity": False},
        evidence=[evidence],
    )
    state = new_recovery_state(
        session_id="g4-serde-integration-test", trace_id="t1", now=now
    )
    state["candidates"] = [proposal]

    # A fresh thread_id/checkpoint id per run, not a fixed literal — reusing
    # one across runs collided with a prior run's row (found live, not
    # assumed): `aget` without an explicit `checkpoint_id` in `config`
    # returns the most recently INSERTED row, and a rerun using the same
    # checkpoint id landed a genuinely stale value the first time this test
    # was run twice in a row.
    thread_id = f"g4-serde-integration-test-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    async with get_checkpointer(dsn, serde=recovery_state_serde()) as saver:
        checkpoint = {
            "v": 1,
            "id": str(uuid.uuid4()),
            "ts": now.isoformat(),
            "channel_values": {"state": state},
            "channel_versions": {"state": "1"},
            "versions_seen": {},
        }
        await saver.aput(config, checkpoint, {}, {"state": "1"})

        stored = await saver.aget(config)
        assert stored is not None
        restored_state = stored["channel_values"]["state"]

        assert restored_state == state
        assert isinstance(restored_state["candidates"][0], ActionProposal)
        assert restored_state["candidates"][0].evidence[0].price == Decimal("39.99")
