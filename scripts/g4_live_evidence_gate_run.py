"""One live run against the hero cart, proving the real read chain ->
Evidence Gate -> rank -> `ActionProposal` pipeline survives real MCP data,
not just the tracked fixtures `test_graph_pipeline_reaches_awaiting_consent.py`
already covers offline. The complementary cases (zero candidates when
`find_products_batch` returns nothing; a well-formed-but-false candidate
rejected) are already proven offline in
`tests/unit/test_evidence_gate_rejects_wellformed_false_value.py` and
`test_evidence_gate_requires_typed_call_provenance.py` — this script exists
only for the part those tests structurally cannot cover: real MCP response
shapes, not a hand-typed fixture.

Deliberately uses FAKE `planner_call`/`explainer_call` (no live LLM) —
this is about the Evidence Gate surviving live MCP data, not a second live
LLM spend on top of IV-05's already-approved smoke. The fake planner
searches for the cart's own line-item names, so `find_products_batch` has
a realistic chance of matching something.

Read-only: every MCP call here is one of the five read-chain tools
(`silpo_get_my_shopping_cart`, `silpo_get_shopping_cart_by_id`,
`silpo_get_available_delivery_types`, `silpo_get_time_slots`,
`silpo_find_products_batch`) — none is a write tool. Reuses
`scripts/capture_fixture.py`'s already-proven live-connection pattern
(fresh session per call, disk-cached OAuth token) rather than inventing a
new one.

Never run by the offline gate or any automated test — needs a real,
already-authenticated Silpo MCP account (`.cache/silpo_mcp_token.json`).
Prints a summary; writes the full final state to
`datasets/evidence/g4_live_run_<timestamp>.json` (gitignored).
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT, load_env  # noqa: E402
from src.lantern.graph.build import build_recovery_graph  # noqa: E402
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent  # noqa: E402
from src.lantern.graph.state import RecoveryState, new_recovery_state  # noqa: E402
from src.lantern.mcp.auth import (  # noqa: E402
    DiskTokenStorage,
    build_redirect_handler,
    callback_handler,
)
from src.lantern.mcp.client import (  # noqa: E402
    compute_schema_hash,
    raise_on_tool_error,
)
from src.lantern.policies.loader import load_registry  # noqa: E402

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
    """Bridges the async MCP call into the sync `Callable` shape the graph
    nodes expect. `asyncio.run` wraps any exception raised inside the
    SDK's own `anyio` task group (the streamable-HTTP transport's session
    teardown) in an `ExceptionGroup`, not the original exception itself —
    a plain `except McpAdapterError` in a node never sees it. Unwrap a
    single-exception group back to its real cause so the node's own
    per-channel error handling actually receives it.
    """
    print(f"  MCP call: {tool_name}({arguments})")
    try:
        return asyncio.run(_call_tool(tool_name, arguments))
    except* Exception as eg:
        # Nested `anyio` task groups (streamable-HTTP transport, then the
        # session's own group) wrap a single real exception in more than
        # one layer of `ExceptionGroup` — descend until an actual
        # exception (or a genuinely multi-cause group) is left.
        cause: BaseException = eg
        while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
            cause = cause.exceptions[0]
        raise cause from None


def _fake_planner(state: RecoveryState) -> SearchIntent:
    """No live LLM call — search for the cart's own real line-item names,
    the same recall a live planner would reasonably reach for near-miss
    gap-clearing, without a second IV-05 spend on top of this already-narrow
    live-MCP scope."""
    cart = state["cart"]
    names = [li.name for li in cart.products][:5] if cart else []
    if not names:
        names = ["хліб"]  # fallback: cart has no line items to search near
    return SearchIntent(search_terms=names, quantity_hint=1)


def _fake_explainer(proposal: Any) -> ExplainerOutput:
    return ExplainerOutput(
        action_id=proposal.action_id,
        guest_text_uk=(
            f"Кандидат: {proposal.product_name} (+{proposal.expected_delta} грн)."
        ),
    )


def _fetch_time_slots(branch_id: str, types: Sequence[str]) -> Dict[str, Any]:
    return _sync_call(
        "silpo_get_time_slots", {"branchId": branch_id, "deliveryTypes": list(types)}
    )


def _fetch_find_products_batch(
    branch_id: str,
    delivery_type: str,
    start: str,
    end: str,
    products: Sequence[str],
) -> Dict[str, Any]:
    return _sync_call(
        "silpo_find_products_batch",
        {
            "branchId": branch_id,
            "deliveryType": delivery_type,
            "timeslotStart": start,
            "timeslotEnd": end,
            "products": list(products),
        },
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    # Without this, LANGSMITH_TRACING never reaches the process environment
    # and `traceable()` silently no-ops (measured: a live run without this
    # call produced zero LangSmith traces even though the graph itself ran
    # correctly — MCP calls don't need `.env` at all, which is why the
    # missing call went unnoticed until checked against the API directly).
    load_env()

    graph = build_recovery_graph(
        fetch_my_cart=lambda: _sync_call("silpo_get_my_shopping_cart", {}),
        fetch_cart_by_id=lambda cart_id: _sync_call(
            "silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id}
        ),
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _sync_call(
            "silpo_get_available_delivery_types", {"latitude": lat, "longitude": lon}
        ),
        fetch_time_slots=_fetch_time_slots,
        fetch_find_products_batch=_fetch_find_products_batch,
        planner_call=_fake_planner,
        explainer_call=_fake_explainer,
        now=lambda: datetime.now(timezone.utc),
        # Fake ids/hash on purpose here would defeat the point: this run's
        # own job (schema-drift quarantine, criterion 8) is to prove the
        # REAL tracked schema hash actually reaches the trace's version
        # tuple, checkable by a human in the LangSmith UI afterward.
        planner_model_id="fake-planner (no live LLM call this run)",
        explainer_model_id="fake-explainer (no live LLM call this run)",
        tools_schema_hash=compute_schema_hash(
            json.loads(
                (
                    PROJECT_ROOT
                    / "tests"
                    / "contract"
                    / "fixtures"
                    / "tools_list_2026-09-05.json"
                ).read_text(encoding="utf-8")
            )["payload"]["tools"]
        ),
        trace_tags=["g4-live-evidence-gate", "criterion-8"],
    )

    initial_state = new_recovery_state(
        session_id="g4-live", trace_id="g4-live", now=datetime.now(timezone.utc)
    )
    print("Invoking the live read -> diagnose -> ... -> explain pipeline...\n")
    # Tags passed to `build_recovery_graph` only reach the two spans
    # `traced_llm_call` wraps (planner, explainer) — the root LangGraph run
    # and its own per-node spans (plan, explain, collect_and_gate, ...) are
    # a separate, outer trace that LangGraph auto-instruments itself, and
    # need the tag passed through `invoke`'s own `config` to carry it too
    # (measured: without this, the root run and every node span showed
    # `tags: []` in LangSmith even though the two LLM leaf spans had them).
    final_state = graph.invoke(
        initial_state, config={"tags": ["g4-live-evidence-gate", "criterion-8"]}
    )

    print(f"\nstatus: {final_state['status']}")
    if final_state.get("error"):
        print(f"error: {final_state['error']}")
    diagnosis = final_state.get("diagnosis")
    if diagnosis is not None:
        print(f"primary_code: {diagnosis.primary_code}  gap: {diagnosis.gap}")
    print(f"channel_comparison rows: {len(final_state.get('channel_comparison', []))}")

    candidates = final_state.get("candidates", [])
    print(f"\nActionProposal candidates surviving the Evidence Gate: {len(candidates)}")
    for c in candidates:
        print(
            f"  - {c.product_name}: +{c.expected_delta} грн (action_id={c.action_id})"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"g4_live_run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    summary: Dict[str, Any] = {
        "status": final_state["status"],
        "error": final_state.get("error"),
        "primary_code": diagnosis.primary_code if diagnosis else None,
        "gap": str(diagnosis.gap) if diagnosis else None,
        "channel_comparison_rows": len(final_state.get("channel_comparison", [])),
        "candidates": [
            {
                "product_name": c.product_name,
                "expected_delta": str(c.expected_delta),
                "action_id": c.action_id,
            }
            for c in candidates
        ],
    }
    out_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
