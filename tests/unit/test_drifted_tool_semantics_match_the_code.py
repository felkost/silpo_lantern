"""the four unreviewed drifted tools' new text
is not just longer prose -- it states TWO semantics the code already
depends on, and this pins that the tracked fixture's own wording still
agrees with what the code implements. If a future fixture refresh changes
either sentence, this test is what forces a re-check rather than letting
the drift pass silently as "just descriptions".

1. `silpo_find_products_batch`'s WEIGHTED PRODUCT UNITS clause: step and
   quantity for a weighted product are ALWAYS in kilograms, regardless of
   what `displayRatio` shows. `action_proposal_builder.build_action_proposals`
   already treats `raw.step` as the direct unit to round a weighted
   quantity to (`unit = raw.step if (raw.weighted and raw.step) else
   Decimal(1)`) -- correct only if the tool's own step field really is in
   the same unit as the quantity the write tool expects, which is exactly
   what this clause states.

2. `silpo_get_time_slots`'s MIN ORDER COST clause: `slots[].minOrderCost`
   only exists in THIS tool's response. `diagnosis.diagnose` falls back to
   `cart.min_order_cost` (populated from a time-slots fetch) as
   `threshold_source="time_slots"` precisely because no other tool exposes
   it -- if the fixture ever stopped saying this, the fallback's own
   justification would need re-deriving, not just its code.
"""

from src.lantern.config import PROJECT_ROOT

_FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-07.json"
)


def _description(tool_name: str) -> str:
    import json

    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for tool in payload["payload"]["tools"]:
        if tool["name"] == tool_name:
            return str(tool.get("description", ""))
    raise AssertionError(f"{tool_name} not found in {_FIXTURE_PATH}")


def test_weighted_units_are_stated_as_kilograms_matching_the_step_unit_code() -> None:
    text = _description("silpo_find_products_batch")
    assert "ALWAYS expressed in KILOGRAMS" in text
    assert "displayRatio" in text and "does NOT mean step is in units of" in text

    # The code's own reliance, re-derived so this test fails if EITHER
    # side changes without the other being re-checked: `raw.step` is used
    # directly as the rounding unit for a weighted quantity.
    from src.lantern.domain.action_proposal_builder import _quantity_that_closes
    from decimal import Decimal

    result = _quantity_that_closes(
        gap=Decimal("10"),
        price=Decimal("5"),
        existing_quantity=Decimal("0"),
        unit=Decimal("0.35"),
    )
    assert result % Decimal("0.35") == 0


def test_min_order_cost_is_exclusive_to_time_slots_matching_the_fallback() -> None:
    text = _description("silpo_get_time_slots")
    assert "minOrderCost only exists in this tool's response" in text

    # The code's own reliance: diagnose() falls back to cart.min_order_cost
    # (populated from a time-slots fetch) exactly when the validation's own
    # context carries no threshold -- see diagnosis.py's threshold_source.
    from src.lantern.domain.diagnosis import diagnose
    from src.lantern.domain.models import Cart, Validation
    from src.lantern.policies.loader import load_registry
    from decimal import Decimal

    cart = Cart(
        cart_id="cart-1",
        products_total=Decimal("35.00"),
        min_order_cost=Decimal("599"),
        validations=[
            Validation(
                level="error",
                type="order",
                code="order.cost.min",
                context={},  # no orderCostMin in the validation itself
            )
        ],
    )
    diagnosis = diagnose(cart, load_registry())
    assert diagnosis.threshold_source == "time_slots"
    assert diagnosis.gap == Decimal("564.00")
