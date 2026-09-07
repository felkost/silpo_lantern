"""Criterion A6's restore write: puts the author's cart back the way a
recorded write found it.

**Why this is a script and not a graph node.** `CLAUDE.md`'s invariant is
that only one node in the graph may call a write tool, and the Write Guard's
allowlist holds exactly one: `silpo_add_or_update_cart_products`. Restoring
sometimes needs `silpo_remove_cart_products`, which the live server marks
`destructiveHint: true` -- because a write that ADDED a line cannot be undone
by the allowlisted tool at all: its own schema sets `exclusiveMinimum: 0` on
`quantity`, so "set this line to zero" is unrepresentable.

Putting a destructive tool in the agent's allowlist to solve an operator's
clean-up problem would widen the one surface this project protects hardest.
So the agent still knows exactly one write tool, and undoing an experiment
stays what it has been all along -- something the author does deliberately,
now with a script instead of by hand.

**What keeps this safe.** It refuses to touch anything this project did not
record writing: the action id must resolve to a receipt, and the product,
quantity and cart must still match what that receipt says the write
produced. If the cart moved since, it stops rather than guessing -- the same
rule the Write Guard applies to `state_hash`.

Read-write against a real cart, so it is author-run, never self-initiated,
and does nothing at all without `--confirm`.

Usage:
    .venv/Scripts/python.exe scripts/g5_restore_after_write.py \
        --action-id <uuid> [--confirm]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from src.lantern.config import (  # noqa: E402
    PROJECT_ROOT,
    get_database_url,
    load_env,
    strip_sqlalchemy_dialect,
)
from src.lantern.mcp.session import call_tool  # noqa: E402
from src.lantern.mcp.production_fetchers import (  # noqa: E402
    fetch_cart_by_id,
    fetch_my_cart,
)

ADD_TOOL = "silpo_add_or_update_cart_products"
REMOVE_TOOL = "silpo_remove_cart_products"


def _load_write(dsn: str, action_id: str) -> Dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        receipt = conn.execute(
            "SELECT before_state, after_state, status FROM receipts"
            " WHERE action_id = %s",
            (action_id,),
        ).fetchone()
        consent = conn.execute(
            "SELECT canonical_args FROM consents WHERE action_id = %s",
            (action_id,),
        ).fetchone()
    if receipt is None or consent is None:
        raise SystemExit(
            f"no receipt/consent recorded for {action_id} — this script only "
            "undoes writes this project performed"
        )
    return {"receipt": receipt, "consent": consent}


def _original_quantity(before_state: Dict[str, Any], product_id: str) -> Decimal:
    for item in (before_state or {}).get("products", []):
        if item.get("product_id") == product_id:
            return Decimal(str(item["quantity"]))
    return Decimal(0)


def _current_quantity(cart: Dict[str, Any], product_id: str) -> Optional[Decimal]:
    for shipment in cart.get("shipments", []):
        for item in shipment.get("products", []):
            if item.get("productId") == product_id:
                return Decimal(str(item["quantity"]))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-id", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="actually send the restore write; without it, only the plan is shown",
    )
    args = parser.parse_args()

    load_env()
    dsn = strip_sqlalchemy_dialect(get_database_url())
    recorded = _load_write(dsn, args.action_id)
    product = recorded["consent"]["canonical_args"]["products"][0]
    product_id = product["productId"]
    written_quantity = Decimal(str(product["quantity"]))
    original = _original_quantity(recorded["receipt"]["before_state"], product_id)

    cart = fetch_cart_by_id(fetch_my_cart()["shoppingCartId"])["cart"]
    cart_id = cart["id"]
    current = _current_quantity(cart, product_id)

    print(f"action:          {args.action_id}")
    print(f"product:         {product_id}")
    print(f"quantity before: {original}")
    print(f"quantity written:{written_quantity}")
    print(f"quantity now:    {current}")

    if current is None:
        raise SystemExit("the product is no longer in the cart — nothing to restore")
    if current != written_quantity:
        raise SystemExit(
            f"the cart has moved since the write ({current} now, {written_quantity} "
            "written) — refusing to guess, restore it by hand"
        )

    if original > 0:
        tool = ADD_TOOL
        payload: Dict[str, Any] = {
            "shoppingCartId": cart_id,
            "products": [
                {
                    "productId": product_id,
                    "companyId": product["companyId"],
                    "branchId": product["branchId"],
                    "quantity": (
                        int(original) if original == int(original) else float(original)
                    ),
                    "addQuantity": False,
                }
            ],
        }
    else:
        tool = REMOVE_TOOL
        payload = {"shoppingCartId": cart_id, "products": [{"productId": product_id}]}

    print(f"\nrestore call:    {tool}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.confirm:
        print("\nDry run. Re-run with --confirm to send it.")
        return

    response = call_tool(tool, payload)
    print("\nwrite response:", json.dumps(response, ensure_ascii=False)[:200])

    # The server's own answer proves nothing (CLAUDE.md): read the cart back.
    after = fetch_cart_by_id(fetch_my_cart()["shoppingCartId"])["cart"]
    restored = _current_quantity(after, product_id)
    print(f"quantity after read-back: {restored}")
    ok = restored == (original if original > 0 else None)
    print("restored:", "YES" if ok else "NO — check the cart by hand")

    evidence = PROJECT_ROOT / "datasets" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = evidence / f"g5_a6_restore_{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "criterion": "A6 restore write",
                "action_id": args.action_id,
                "tool": tool,
                "payload": payload,
                "quantity_before_original_write": str(original),
                "quantity_after_restore": str(restored),
                "restored": ok,
                "products_total_after": after["calculation"]["productsTotal"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("evidence written:", out.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
