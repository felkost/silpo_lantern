"""Probe P1 (blocking): does `silpo_find_products_batch`'s
`products[].id` share the write tool's identifier space with the cart's own
`shipments[].products[].productId`? Are `companyId`/`branchId` populated in
practice? This settles an earlier decision before any Write Guard code is
written against an assumed answer.

Read-only, no LLM spend. Reuses `scripts/g4_live_evidence_gate_run.py`'s
already-proven live-connection pattern (fresh session per call, disk-cached
OAuth token, the exception-group unwrap) rather than inventing a new one.

Author-run per the stage spec's own §10 ("Handed over, not run") — the
assistant does not self-initiate a live MCP call.

Usage:
    .venv/Scripts/python.exe scripts/g5_probe_p1_find_products_batch_shape.py

Writes the full raw response and this script's own analysis to
`datasets/evidence/g5_probe_p1_<timestamp>.json` (gitignored, like every
other raw live-run record this project keeps).
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT, load_env  # noqa: E402
from src.lantern.domain.normalizer import normalize_cart  # noqa: E402
from src.lantern.mcp.auth import (  # noqa: E402
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)
from src.lantern.mcp.client import raise_on_tool_error  # noqa: E402

DEFAULT_MCP_URL = "https://mcp.silpo.ua/mcp"
OUT_DIR = PROJECT_ROOT / "datasets" / "evidence"


async def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from mcp.client.auth.oauth2 import OAuthClientProvider
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.shared.auth import OAuthClientMetadata
    from pydantic import AnyUrl

    storage = DiskTokenStorage()
    auth = OAuthClientProvider(
        server_url=DEFAULT_MCP_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[AnyUrl("https://localhost/callback")],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=build_redirect_handler(storage),
        callback_handler=callback_handler,
    )
    async with streamablehttp_client(DEFAULT_MCP_URL, auth=auth) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            raise_on_tool_error(result)
            return result.structuredContent or {}


def _sync_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Same recursive `BaseExceptionGroup` unwrap as
    `g4_live_evidence_gate_run.py`'s `_sync_call` — measured
    necessary for this exact async/sync bridge, not copied on faith."""
    print(f"  MCP call: {tool_name}({arguments})")
    try:
        return asyncio.run(_call_tool(tool_name, arguments))
    except* Exception as eg:
        cause: BaseException = eg
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        raise cause from None


def main() -> None:
    load_env()
    print("Reading the real cart...")
    my_cart = _sync_call("silpo_get_my_shopping_cart", {})
    cart_id = my_cart["shoppingCartId"]
    full = _sync_call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id})
    cart = normalize_cart(full["cart"])

    if not cart.products:
        print("Cart has no line items — cannot answer P1. Add an item first.")
        sys.exit(1)

    line_item = cart.products[0]
    print(
        f"Probing against cart line item: {line_item.name!r} "
        f"(cart productId={line_item.product_id}, "
        f"companyId={line_item.company_id}, branchId={line_item.branch_id})"
    )

    search_terms = [line_item.name]
    batch_args = {
        "branchId": cart.branch_id or "",
        "deliveryType": cart.delivery_type or "",
        "timeslotStart": cart.timeslot_start.isoformat() if cart.timeslot_start else "",
        "timeslotEnd": cart.timeslot_end.isoformat() if cart.timeslot_end else "",
        "products": search_terms,
    }
    response = _sync_call("silpo_find_products_batch", batch_args)

    products: list[Dict[str, Any]] = []
    for query in response.get("queries", []):
        products.extend(query.get("products", []))

    analysis = {
        "cart_line_item": {
            "product_id": line_item.product_id,
            "company_id": line_item.company_id,
            "branch_id": line_item.branch_id,
            "name": line_item.name,
        },
        "find_products_batch_result_count": len(products),
        "per_product_analysis": [],
    }

    for p in products:
        matches_cart_product_id = str(p.get("id")) == str(line_item.product_id)
        analysis["per_product_analysis"].append(
            {
                "id": p.get("id"),
                "id_is_uuid_shaped": _looks_like_uuid(p.get("id")),
                "matches_cart_line_item_product_id": matches_cart_product_id,
                "companyId": p.get("companyId"),
                "branchId": p.get("branchId"),
                "externalProductId": p.get("externalProductId"),
                "stock": p.get("stock"),
                "weighted": p.get("weighted"),
                "step": p.get("step"),
                "available": p.get("available"),
            }
        )

    print(json.dumps(analysis, ensure_ascii=False, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"g5_probe_p1_{ts}.json"
    out_path.write_text(
        json.dumps(
            {"raw_response": response, "analysis": analysis},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWritten to {out_path}")


def _looks_like_uuid(value: Any) -> bool:
    import re

    if not isinstance(value, str):
        return False
    return bool(
        re.match(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
            value,
        )
    )


if __name__ == "__main__":
    main()
