"""Money-is-Decimal, measured directly rather
than assumed: constructing `EvidenceTuple` through its normal Pydantic
validator (never `model_construct`, which would bypass validation) already
routes a raw JSON float through the same safe path `to_money` uses —
`Decimal(str(value))`, not `Decimal(value)` directly. Measured on a value
where the two paths actually diverge (`0.1 + 0.2 == 0.30000000000000004`
in IEEE-754 double precision); on a "nice" price like `39.99` both paths
happen to agree, which would have hidden this exact class of bug.

This is why the Evidence Gate (`src/lantern/domain/evidence_gate.py`) never
needs its own manual `to_money` call for `price` — the guarantee already
lives in the model, and this test is what makes that a checked fact rather
than a hopeful assumption.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import EvidenceTuple


def test_pydantic_decimal_coercion_matches_the_str_first_path_on_imprecise_float() -> (
    None
):
    imprecise_float = 0.1 + 0.2  # 0.30000000000000004 — a genuine float artifact
    assert Decimal(imprecise_float) != Decimal(str(imprecise_float)), (
        "test setup assumption broken: this float no longer demonstrates the "
        "binary-vs-string Decimal divergence it's chosen for"
    )

    tuple_ = EvidenceTuple(
        product_id="p1",
        price=imprecise_float,
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=datetime.now(timezone.utc),
    )

    assert tuple_.price == Decimal(str(imprecise_float))
    assert tuple_.price != Decimal(imprecise_float)
