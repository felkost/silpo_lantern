"""G3-F15: the independent oracle (`tests/unit/oracle.py`) and the domain
implementation must agree on the gap for the same raw cart — checked
against the tracked D12 fixture and the boundary generator's own output,
not by re-reading either implementation.
"""

import json
from decimal import Decimal
from pathlib import Path

from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.normalizer import CartShapeError, normalize_cart
from src.lantern.policies.loader import load_registry
from tests.unit.oracle import oracle_gap

_D12_FIXTURE = Path(__file__).parent / "fixtures" / "d12_cart_wire_shape.json"


def test_oracle_agrees_on_d12_fixture() -> None:
    raw = json.loads(_D12_FIXTURE.read_text(encoding="utf-8"))

    oracle_value = oracle_gap(raw)
    domain_value = diagnose(normalize_cart(raw), load_registry()).gap

    assert oracle_value == Decimal("194.11")
    assert oracle_value == domain_value


def test_oracle_agrees_on_generated_boundary_fixtures() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.generate_boundary_fixtures import generate

    registry = load_registry()
    envelopes, _ = generate(seed=20260907)

    for envelope in envelopes:
        raw = envelope["payload"]
        oracle_value = oracle_gap(raw)
        try:
            cart = normalize_cart(raw)
        except CartShapeError:
            # A scenario the normalizer deliberately can't build a Cart
            # from at all — nothing to compare in that case.
            continue
        domain_value = diagnose(cart, registry).gap
        assert oracle_value == domain_value, envelope["fixture_id"]
