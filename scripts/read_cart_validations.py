"""Disclosure audit, step 2: reads what the cart actually carries, at the
moment the observer is looking at the app.

READ-ONLY. It calls `silpo_get_my_shopping_cart` and
`silpo_get_shopping_cart_by_id` and nothing else -- no write tool is
imported, let alone called, so this can be run beside a live audit without
the cart moving underneath it.

Writes one observation record per run to the gitignored evidence
directory. The record carries the validation CODES and the cart's own
totals, never the address or any identifier: the audit compares what the
app renders against what the data holds, and neither question needs to
know where the guest lives.

Usage:
    .venv/Scripts/python.exe -m scripts.read_cart_validations --state 1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.lantern.config import PROJECT_ROOT, load_env

EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"


def _validation_rows(cart: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every validation the cart carries, with the context the app would
    need in order to render a useful message.

    `context` is kept because a code alone cannot say whether a message
    was adequate: `order.cost.min` with `orderCostMin: 699` is a
    constraint the app could state precisely, and an app that says only
    "add more items" has rendered the code without the fact.
    """
    rows = []
    for validation in cart.get("calculation", {}).get("validations", []):
        rows.append(
            {
                # The code lives in `message`, NOT in `code` -- the live
                # server puts the identifier there and leaves `code`
                # absent. Read from `code` and every row comes back None,
                # which is how the first run of this script reported two
                # nameless validations. `sanitizer`/`diagnosis` already
                # read `message`; this script had invented its own field.
                "code": validation.get("message") or validation.get("code"),
                "level": validation.get("level"),
                "type": validation.get("type"),
                "context": validation.get("context"),
                "product_id_present": bool(
                    (validation.get("context") or {}).get("productId")
                ),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        required=True,
        help="the state id from the audit protocol (1-4)",
    )
    parser.add_argument(
        "--note",
        default="",
        help="anything about the moment worth recording",
    )
    args = parser.parse_args()

    load_env()
    from src.lantern.mcp.production_fetchers import fetch_cart_by_id, fetch_my_cart

    cart_id = fetch_my_cart()["shoppingCartId"]
    cart = fetch_cart_by_id(cart_id)["cart"]
    calculation = cart.get("calculation", {})
    validations = _validation_rows(cart)

    record = {
        "state_id": args.state,
        "read_at": datetime.now(timezone.utc).isoformat(),
        "note": args.note,
        "products_total": calculation.get("productsTotal"),
        "total": calculation.get("total"),
        "total_after_discounts": calculation.get("totalAfterDiscounts"),
        "delivery_total": (calculation.get("delivery") or {}).get("total"),
        "line_count": sum(
            len(shipment.get("products", [])) for shipment in cart.get("shipments", [])
        ),
        "validations": validations,
        "distinct_codes": sorted(
            {v["code"] for v in validations if v["code"] is not None}
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = EVIDENCE_DIR / f"disclosure_cart_state{args.state}_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"state {args.state}: productsTotal {record['products_total']}, "
        f"{record['line_count']} line(s)"
    )
    print(f"validations carried: {len(validations)}")
    for validation in validations:
        print(
            f"  {validation['code']}  level={validation['level']}  "
            f"context={validation['context']}"
        )
    # Level is not decoration: an `error` blocks checkout, an `info` is a
    # note about something optional. Counting the two together is how a
    # code name becomes a story it does not support.
    errors = [v for v in validations if v["level"] == "error"]
    print(
        f"\nblocking (level=error): {len(errors)} -- "
        f"{[v['code'] for v in errors] or 'none'}"
    )
    print(f"\nwrote {out.relative_to(PROJECT_ROOT)}")
    print(
        "Do NOT read this out to the observer until they have recorded what "
        "the app shows -- the audit's question is what an unprompted guest "
        "would notice."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
