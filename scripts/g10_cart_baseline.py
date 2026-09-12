"""brings the author's cart to the demo baseline -- a valid delivery
slot -- and reports what else stands between the cart and the hero
scenario. The pair of `g5_restore_after_write.py`: that one undoes what
a demo wrote, this one prepares the cart before it.

**Why a slot and nothing else.** The first console session showed a
cart with a lapsed slot and ten `product.offer.stock.max` lines; setting
the slot alone made all ten disappear -- stock was being evaluated
against a slot that no longer existed. So the one write this script may
make is `silpo_update_shopping_cart` with a new timeslot, copying delivery
type, address and shipments from the cart as-is (the tool's own
instruction). It never removes a product: the agent's allowlist holds one
write tool, the restore script holds the destructive one for recorded
writes only, and a demo operator deleting arbitrary lines by script is a
third surface this project does not want. Lines that still fail after the
slot are listed for the author to fix in the app.

**What keeps it safe.** Without `--confirm` it reads, decides and prints
the exact call it would make. It refuses to touch a cart whose only
problem is not the slot. It prints no address, no coordinates and no cart
id. Author-run, never self-initiated.

Usage:
    .venv/Scripts/python.exe -m scripts.g10_cart_baseline            # plan only
    .venv/Scripts/python.exe -m scripts.g10_cart_baseline --confirm  # one write
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import load_env  # noqa: E402

SLOT_CODES = {"timeslot.not_found", "timeslot.not_available"}


def needs_new_slot(validations: Sequence[Mapping[str, Any]]) -> bool:
    return any(v.get("code") in SLOT_CODES for v in validations)


def pick_slot(
    slots: Sequence[Mapping[str, Any]], *, now_iso: str
) -> Optional[Dict[str, str]]:
    """The first slot the server marks available that starts after now."""
    now = datetime.fromisoformat(now_iso)
    for slot in slots:
        if not slot.get("available"):
            continue
        try:
            start = datetime.fromisoformat(str(slot["start"]))
        except (KeyError, ValueError):
            continue
        if start > now:
            return {"start": str(slot["start"]), "end": str(slot["end"])}
    return None


def _validations(cart: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for v in cart.get("calculation", {}).get("validations", []):
        rows.append(
            {
                "code": v.get("message") or v.get("code"),
                "level": v.get("level"),
                "context": v.get("context") or {},
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="perform the one write")
    args = parser.parse_args()

    from src.lantern.mcp.production_fetchers import (
        fetch_cart_by_id,
        fetch_my_cart,
        fetch_time_slots,
    )
    from src.lantern.mcp.session import call_tool

    load_env()
    mine = fetch_my_cart()
    cart_id = str(mine.get("shoppingCartId") or mine.get("id") or mine.get("cartId"))
    cart = fetch_cart_by_id(cart_id)
    cart = cart.get("cart", cart)
    validations = _validations(cart)
    total = cart.get("calculation", {}).get("productsTotal")
    print(f"productsTotal {total}, validations: {[v['code'] for v in validations]}")

    if not needs_new_slot(validations):
        print("slot is valid -- nothing to write.")
        _report_remaining(validations)
        return 0

    branch = cart["shipments"][0]["branchId"]
    slots = fetch_time_slots(branch, [cart["deliveryType"]]).get("slots", [])
    chosen = pick_slot(slots, now_iso=datetime.now(timezone.utc).isoformat())
    if chosen is None:
        print("no available slot returned by the server -- stop.")
        return 1
    print(f"would set timeslot {chosen['start']} -> {chosen['end']}")
    if not args.confirm:
        print("plan only; re-run with --confirm to write.")
        return 0

    result = call_tool(
        "silpo_update_shopping_cart",
        {
            "shoppingCartId": cart_id,
            "deliveryType": cart["deliveryType"],
            "timeslot": chosen,
            "address": cart["address"],
            "shipments": [
                {k: s[k] for k in ("companyId", "branchId") if k in s}
                for s in cart["shipments"]
            ],
        },
    )
    print("write response success:", result.get("success"))
    after = fetch_cart_by_id(cart_id)
    after = after.get("cart", after)
    after_validations = _validations(after)
    print(
        f"read-back: timeslot {after.get('timeslot')}, "
        f"validations: {[v['code'] for v in after_validations]}"
    )
    _report_remaining(after_validations)
    return 0


def _report_remaining(validations: Sequence[Mapping[str, Any]]) -> None:
    stock = [v for v in validations if v["code"] == "product.offer.stock.max"]
    if stock:
        print(
            f"{len(stock)} line(s) still out of stock -- remove or reduce them in the "
            "app; this script never deletes a product."
        )
    if any(v["code"] == "order.cost.min" for v in validations):
        print("order.cost.min present: the cart is at the hero baseline.")


if __name__ == "__main__":
    sys.exit(main())
