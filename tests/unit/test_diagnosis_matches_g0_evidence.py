"""Reproduces the gap and the three-channel table
from a live evidence run, from a **tracked**
fixture (`tests/unit/fixtures/d12_cart_wire_shape.json`) — never by
reading the gitignored local evidence directory, which is absent on a
fresh clone.

Expected numbers are literal constants matching the live run exactly:
gap 194.11 (599 - 404.89), and the three-channel table
699/599/199 -> 294.11/194.11/-205.89.
"""

import json
from decimal import Decimal
from pathlib import Path

from src.lantern.domain.disclosure import ChannelSnapshot, compare_channels
from src.lantern.domain.normalizer import normalize_cart
from src.lantern.policies.loader import load_registry
from src.lantern.domain.diagnosis import diagnose

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "d12_cart_wire_shape.json"


def test_gap_reproduces_g0_02_d12() -> None:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    cart = normalize_cart(raw)
    diagnosis = diagnose(cart, load_registry())

    # 599 - 404.89 = 194.11
    assert diagnosis.gap == Decimal("194.11")
    assert diagnosis.primary_code == "order.cost.min"


def test_three_channel_comparison_reproduces_d12_table() -> None:
    # The three-channel table, DeliveryHome/NovaPoshta/SelfPickup.
    products_total = Decimal("404.89")
    snapshots = [
        ChannelSnapshot(
            delivery_type="DeliveryHome",
            branch_id="branch-home",
            branch_is_inferred=False,
            min_order_cost=Decimal("699"),
            delivery_cost=Decimal("99"),
            delivery_cost_map=[],
            slots_total=27,
            slots_free=18,
            item_availability=[True],
        ),
        ChannelSnapshot(
            delivery_type="NovaPoshta",
            branch_id="branch-novaposhta",
            branch_is_inferred=True,  # guessed branch
            min_order_cost=Decimal("599"),
            delivery_cost=Decimal("129"),
            delivery_cost_map=[],
            slots_total=7,
            slots_free=2,
            item_availability=[True],
        ),
        ChannelSnapshot(
            delivery_type="SelfPickup",
            branch_id="branch-selfpickup",
            branch_is_inferred=False,
            min_order_cost=Decimal("199"),
            delivery_cost=Decimal("9"),
            delivery_cost_map=[],
            slots_total=5,
            slots_free=3,
            item_availability=[True],
        ),
    ]

    rows = compare_channels(products_total, snapshots)
    gaps = [row.gap for row in rows]

    assert gaps == [Decimal("294.11"), Decimal("194.11"), Decimal("-205.89")]
    # DeliveryHome and NovaPoshta both fail to clear on price alone;
    # NovaPoshta additionally carries an inferred branch.
    assert rows[0].verdict == "needs_check"
    assert rows[1].verdict == "needs_check"
    assert "branch_is_inferred" in rows[1].reason
    # SelfPickup clears on every measured signal.
    assert rows[2].verdict == "clears_now"
