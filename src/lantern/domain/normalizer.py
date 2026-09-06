"""Normalize a raw MCP cart payload into `Cart`. No
I/O — the caller (an `infra`-layer adapter) is responsible for calling
`silpo_get_shopping_cart_by_id` and unwrapping `CallToolResult.content[0].text`
(a JSON string) into a dict before this module ever sees it
(measured against a live capture on 2026-09-06).

Live wire shape this normalizes (the `cart` key of that tool's parsed
response):

    cart.id, cart.deliveryType, cart.timeslot.{start,end}
    cart.address.{latitude, longitude}         # strings
    cart.calculation.{total, totalAfterDiscounts, subTotal, subDiscount,
                       productsTotal, delivery.total, validations[]}
    cart.shipments[].{id, companyId, branchId, products[]}
    cart.shipments[].products[].{productId, companyId, branchId, name,
                                  quantity, price, subDiscount, stock}
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Union

from src.lantern.domain.models import Cart, LineItem, Money, Validation

MoneyInput = Union[str, int, float, None]


class CartShapeError(ValueError):
    """A raw payload does not match the measured cart shape. Raised naming
    the missing/invalid key rather than defaulting it — a caller that
    wants a diagnosis on malformed input gets a loud, specific failure,
    never a silently wrong `Cart`."""


def to_money(value: MoneyInput) -> Optional[Money]:
    """Money is `Decimal`, never `float` — a raw JSON float is
    routed through `str()` first so its literal decimal digits are kept
    rather than the value's binary floating-point approximation. `None`
    stays `None` (`deliveryCost: null` is "not applicable", not
    zero) — a caller that wants zero must pass zero explicitly."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise CartShapeError(f"not a valid money value: {value!r}") from exc


def to_kyiv_display(value: datetime) -> datetime:
    """Display conversion only — the value stays UTC-aware
    internally; the caller applies `.astimezone(ZoneInfo("Europe/Kyiv"))`
    for rendering. A naive `datetime` is rejected rather than assumed
    UTC: `fromisoformat` on an offset-less string returns naive silently,
    and treating an already-expired slot as still live is the worst
    possible failure direction here."""
    if value.tzinfo is None:
        raise CartShapeError(f"naive datetime is not accepted: {value!r}")
    return value


def _require(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise CartShapeError(f"missing required key {key!r} in {context}")
    return mapping[key]


def _parse_validation(raw: Mapping[str, Any]) -> Validation:
    # The wire field is `message`, never `code` — the live payload
    # has no `code` field at all.
    code = raw.get("message")
    if code is None:
        raise CartShapeError("validation entry missing wire field 'message'")
    # `level` and `type` are read the same fail-loud way as `message` — a
    # bare KeyError here would escape this module's own contract, which is
    # that a malformed payload raises CartShapeError naming the key.
    for required in ("level", "type"):
        if required not in raw:
            raise CartShapeError(f"validation entry missing wire field {required!r}")
    return Validation(
        level=raw["level"],
        type=raw["type"],
        code=code,
        context=raw.get("context") or {},
    )


def _parse_line_item(raw: Mapping[str, Any], branch_id: Optional[str]) -> LineItem:
    return LineItem(
        product_id=_require(raw, "productId", "line item"),
        name=raw.get("name", ""),
        quantity=Decimal(str(raw.get("quantity", 0))),
        price=to_money(raw.get("price")) or Decimal("0"),
        stock=raw.get("stock"),
        sub_discount=to_money(raw.get("subDiscount")),
        company_id=raw.get("companyId"),
        branch_id=raw.get("branchId", branch_id),
    )


def _parse_timeslot(
    raw: Optional[Mapping[str, Any]],
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not raw:
        return None, None
    start = raw.get("start")
    end = raw.get("end")
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    if start_dt is not None:
        to_kyiv_display(start_dt)
    if end_dt is not None:
        to_kyiv_display(end_dt)
    return start_dt, end_dt


def normalize_cart(raw: Mapping[str, Any]) -> Cart:
    """`raw` is the already-parsed `cart` object (see module docstring) —
    not the `CallToolResult` envelope, and not the whole
    `{success, cart, loyalty}` response body.

    Only `calculation.productsTotal` is hard-required — the one field the
    fail-closed guarantee actually depends on. `id` is
    read leniently (`test_dr_01_money_is_decimal.py`'s own minimal fixture
    carries no `id` at all) because a missing
    cart id is a data-completeness question for a caller to decide on, not
    a shape this normalizer cannot make sense of."""
    cart_id = raw.get("id", "")
    calculation = _require(raw, "calculation", "cart")
    products_total = to_money(calculation.get("productsTotal"))
    if products_total is None:
        raise CartShapeError("calculation.productsTotal is missing or null")

    shipments = raw.get("shipments") or []
    line_items: list[LineItem] = []
    shipment_branch_id: Optional[str] = None
    shipment_company_id: Optional[str] = None
    for shipment in shipments:
        shipment_branch_id = shipment.get("branchId", shipment_branch_id)
        shipment_company_id = shipment.get("companyId", shipment_company_id)
        for product in shipment.get("products") or []:
            line_items.append(_parse_line_item(product, shipment.get("branchId")))

    validations = [_parse_validation(v) for v in calculation.get("validations") or []]

    address = raw.get("address") or {}
    latitude = address.get("latitude")
    longitude = address.get("longitude")

    delivery = calculation.get("delivery") or {}
    timeslot_start, timeslot_end = _parse_timeslot(raw.get("timeslot"))

    min_order_cost_raw = raw.get("minOrderCost")
    # minOrderCost sometimes arrives as a per-slot list. A single
    # value is used directly; disagreement inside the list itself is left
    # to diagnosis.py's threshold arbitration rather than resolved
    # here, so the normalizer never silently picks one.
    min_order_cost: Optional[Money]
    if isinstance(min_order_cost_raw, list):
        min_order_cost = (
            to_money(min_order_cost_raw[0]) if len(min_order_cost_raw) == 1 else None
        )
    else:
        min_order_cost = to_money(min_order_cost_raw)

    return Cart(
        cart_id=cart_id,
        branch_id=shipment_branch_id,
        company_id=shipment_company_id,
        delivery_type=raw.get("deliveryType"),
        products_total=products_total,
        total=to_money(calculation.get("total")),
        total_after_discounts=to_money(calculation.get("totalAfterDiscounts")),
        sub_total=to_money(calculation.get("subTotal")),
        latitude=float(latitude) if latitude is not None else None,
        longitude=float(longitude) if longitude is not None else None,
        timeslot_start=timeslot_start,
        timeslot_end=timeslot_end,
        validations=validations,
        products=line_items,
        min_order_cost=min_order_cost,
        delivery_cost=to_money(delivery.get("total")),
        restrictions=list(raw.get("restrictions") or []),
        constraints=dict(raw.get("constraints") or {}),
    )
