"""Plan section 1.5's HTTP contract: `POST /session`, `GET /session/{id}/
events` (SSE), `POST /session/{id}/consent`, `GET /auth/start`,
`GET /auth/callback`. `/health` stays in `main.py` -- it predates this
module and its own docstring's "no I/O" contract is unrelated to session
state.

Live per-node push (revised from the D29 replay-only draft, on the
author's request): `GET /session/{id}/events` is what actually DRIVES the
graph, via `graph.astream(..., stream_mode="updates")` -- measured
(`.venv` probe) to yield one `{node_name: partial_state}` chunk per
completed node, and `{"__interrupt__": ()}` at a pause, with no error and
no partial re-execution. `POST /session` only creates the session row;
`POST /session/{id}/consent` only records consent and advances the
checkpoint's `consent_action_id` -- neither runs the graph. The read
pipeline runs on the FIRST call to `/events` (no checkpoint exists yet);
the write pipeline runs on a LATER call to the same endpoint, once consent
has been recorded (`aget_state` shows an existing, non-empty checkpoint,
so `astream` resumes from it with `None` rather than a fresh state).

`request.app.state.graph_builder` is a zero-argument callable that builds
(and caches) the production graph -- injected this way, not called
directly, so the offline test suite can substitute a fake builder via
`app.state.graph_builder = ...` and never construct a real OpenRouter
client or make a live MCP call.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from apps.api.evidence import load_evidence
from apps.api.schemas import ConsentAckResponse, ConsentRequest, CreateSessionResponse
from apps.api.session_cookie import (
    clear_session_cookie,
    require_session_cookie,
    set_session_cookie,
)
from src.lantern.domain.consent_hash import (
    compute_args_hash,
    compute_owner,
    compute_state_hash,
)
from src.lantern.domain.models import ConsentRecord
from src.lantern.domain.repeat_accounting import TokenUsage, cost_usd
from src.lantern.graph.llm_adapter import current_usage_log, load_llm_prices
from src.lantern.graph.state import (
    ACTIVE_EXECUTION_SECONDS,
    RecoveryState,
    new_recovery_state,
)
from src.lantern.mcp.session import current_token_storage
from src.lantern.mcp.session_token_storage import SessionTokenStorage
from src.lantern.memory import repository
from src.lantern.policies.loader import PolicyRegistry, load_registry

router = APIRouter()

CONSENT_TTL = timedelta(minutes=5)  # plan section 11.1

# G10 (A-G10-01): what kind of I/O each graph node does, for the `stage`
# event -- so the console's loader can say "MCP" / "model" / "database"
# from an observation, not a guess. Keys are the ten names `build.py`
# registers; `write_guard` reads the live tool schema (MCP) and the
# consent row (db). Mirrored client-side in `apps/web/src/stages.ts`.
NODE_IO: Dict[str, str] = {
    "read": "mcp",
    "diagnose": "pure",
    "compare_channels": "mcp",
    "plan": "llm",
    "collect_and_gate": "mcp",
    "rank": "pure",
    "explain": "llm",
    "write_guard": "mcp+db",
    "write_and_readback": "mcp+db",
    "persist_receipt": "db",
}


def _config(thread_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _get_graph(request: Request) -> Any:
    # `graph_builder()` is sync and, on its first (caching) call, reaches
    # `mcp.session.list_tools_raw`, which opens its OWN event loop via
    # `asyncio.run`. Calling it directly from this async route would run
    # that inside uvicorn's already-running loop -- measured: raises
    # "asyncio.run() cannot be called from a running event loop". A worker
    # thread gives it a loop-free thread to open its own loop in, same fix
    # as the sync repository pool already relies on.
    return await asyncio.to_thread(request.app.state.graph_builder)


def _version_tuple(request: Request) -> Dict[str, str]:
    return dict(getattr(request.app.state, "version_tuple", {}))


_registry: Optional[PolicyRegistry] = None


def _is_known(code: str) -> bool:
    # G10: `is_known` per validation on the diagnosis frame -- the same
    # exact-match registry `diagnose()` uses, so the console's "unknown"
    # and the domain's "unknown" cannot disagree. Loaded once.
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry.lookup(code) is not None


def _sse_line(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _caps(request: Request) -> Any:
    return request.app.state.spend_caps


@router.post("/session", response_model=CreateSessionResponse)
async def create_session(request: Request, response: Response) -> CreateSessionResponse:
    # G10 (D89): per-IP cap before any row is written. `request.client`
    # is the proxy on Render unless uvicorn trusts X-Forwarded-For -- see
    # `apps/api/__main__.py`.
    ip = request.client.host if request.client else "unknown"
    if not _caps(request).admit_session(ip):
        raise HTTPException(
            status_code=429, detail="too many sessions from this address today"
        )
    session_id = str(uuid.uuid4())
    thread_id = session_id
    owner = compute_owner(session_id, request.app.state.owner_secret)
    repository.create_session(request.app.state.repo_pool, session_id, thread_id, owner)
    # G10 (A-G10-04): the id travels as a cookie from here on; `/auth/start`
    # reads it from there, so the URL the guest navigates to carries
    # nothing (G10-5).
    set_session_cookie(response, session_id)
    # A brand-new session has no guest token yet, so the client's next
    # step is `/auth/start`, not `/events`. Returned rather than left for
    # the client to infer from a failed stream.
    return CreateSessionResponse(
        session_id=session_id, authorized=False, auth_url="/auth/start"
    )


@router.delete("/session/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request, response: Response) -> None:
    """G10 (A-G10-04): logout. Deletes the guest's token row -- the only
    credential this session holds -- and clears the cookie; a following
    `/events` is refused as unauthorized. The session row and its
    consents/receipts stay as the audit record they are."""
    require_session_cookie(request, session_id)
    repository.delete_session_token(request.app.state.repo_pool, session_id)
    clear_session_cookie(response)


@router.get("/session/{session_id}/events")
async def session_events(session_id: str, request: Request) -> StreamingResponse:
    """Drives the graph one segment further and streams each completed
    node as one of plan section 1.5's five SSE events. Called twice by a
    real client: once right after `POST /session` (runs the read
    pipeline to its `awaiting_consent` pause), and once again after
    `POST /session/{id}/consent` (resumes into the write pipeline to a
    `receipt`/`error` outcome).
    """
    require_session_cookie(request, session_id)
    # Bind THIS guest's own credential BEFORE touching the graph at all --
    # G7/IV-07 found live that `_get_graph` builds the production graph
    # lazily on its OWN first call, ever, across the whole app's lifetime
    # (`app.state.graph` is cached permanently once built), and that
    # build calls `list_tools_raw()` synchronously to seed the tool
    # registry. Binding the token afterward meant the very first guest to
    # hit this route triggered that call with no guest context bound yet,
    # falling back to the single operator token on disk -- invisible in
    # local dev (the operator's own token happens to exist there) but a
    # hard 500 on a host with no such file (Render). Every MCP call the
    # graph makes reads this binding from the context (measured to
    # survive both LangGraph's sync-node execution and the `asyncio.run`
    # inside `mcp.session.call_tool` -- pinned by
    # `tests/unit/test_session_token_contextvar_propagates.py`).
    storage = SessionTokenStorage(request.app.state.repo_pool, session_id)
    if await storage.get_tokens() is None:
        raise HTTPException(
            status_code=401,
            detail="session is not authorized yet -- send the guest to /auth/start",
        )
    current_token_storage.set(storage)

    graph = await _get_graph(request)
    config = _config(session_id)

    snapshot = await graph.aget_state(config)
    existing_state: RecoveryState = snapshot.values

    if not existing_state:
        session_row = repository.get_session(request.app.state.repo_pool, session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail="session not found")
        # G10 (D89): a fresh start is what bills the LLM; a resume or a
        # replay below does not, so only this branch counts.
        if not _caps(request).admit_llm_run():
            raise HTTPException(
                status_code=429, detail="the daily ceiling on live sessions is reached"
            )
        trace_id = str(uuid.uuid4())
        resume_input: Optional[RecoveryState] = new_recovery_state(
            session_id=session_id,
            trace_id=trace_id,
            now=datetime.now(timezone.utc),
            owner=session_row["owner"],
        )
    else:
        resume_input = None  # resume the existing checkpoint
        trace_id = existing_state.get("trace_id", "")

    # A GET must be safe to repeat. Advancing the graph on every call means
    # a browser refresh, a double-clicked button or a retried request
    # resumes past the consent pause into `write_guard` with no consent
    # recorded -- which aborts the session permanently. Measured, not
    # hypothetical: it destroyed a live session during this stage's own
    # verification run. When the graph should not move, the current state
    # is replayed instead.
    status = existing_state.get("status") if existing_state else None
    should_advance = not (
        status == "awaiting_consent" and not existing_state.get("consent_action_id")
    ) and status not in ("aborted", "no_action_available", "verified", "unverified")

    version_tuple = _version_tuple(request)

    # G10 (D90): this run's model calls land here; the frames show the
    # session's cumulative SPEND (checkpoint + this run), never a
    # remainder -- the ceiling is a project decision, the provider's
    # dashboard is the only real balance.
    usage_log: List[Tuple[str, TokenUsage]] = []
    current_usage_log.set(usage_log)
    prices = load_llm_prices()
    prior_tokens = int(existing_state.get("tokens_used", 0) if existing_state else 0)
    prior_cost = float(
        existing_state.get("llm_cost_usd", 0.0) if existing_state else 0.0
    )

    def _spend() -> Dict[str, Any]:
        tokens = prior_tokens + sum(
            u.input_tokens + u.output_tokens for _, u in usage_log
        )
        cost = prior_cost + sum(
            cost_usd(
                u,
                input_usd_per_million=prices[role]["input"],
                output_usd_per_million=prices[role]["output"],
            )
            for role, u in usage_log
        )
        return {
            "tokens": tokens,
            "cost_usd": round(cost, 6),
            "ceiling_usd": prices["ceiling_usd"],
        }

    async def stream() -> AsyncIterator[str]:
        base = {
            "session_id": session_id,
            "trace_id": trace_id,
            "version": version_tuple,
        }

        def _diagnosis_line(
            diagnosis: Any, disclosure: Any, channels: Sequence[Any], cart: Any
        ) -> str:
            # G7 (D-G7-03): carries the disclosure layer and the
            # delivery-channel comparison, not just primary_code/gap --
            # both were already computed for the planner's own prompt
            # (`llm_adapter.py`) and never reached the guest before this.
            # `disclosure` is `DisclosureReport | None`: `diagnose_node`
            # always sets it alongside `diagnosis`, but the accumulator in
            # `stream()` below only calls this once both are non-None.
            return _sse_line(
                "diagnosis",
                {
                    **base,
                    "primary_code": diagnosis.primary_code,
                    "gap": (str(diagnosis.gap) if diagnosis.gap is not None else None),
                    "gap_is_borderline": bool(
                        disclosure and disclosure.gap_is_borderline
                    ),
                    # G10 (claim 2): the arithmetic's inputs, so the panel
                    # can show `threshold - products_total = gap` as code
                    # did it. `products_total` is money, not identity;
                    # the cart's id and coordinates never leave the server.
                    "products_total": (
                        str(cart.products_total) if cart is not None else None
                    ),
                    "threshold_source": diagnosis.threshold_source,
                    "validations": [
                        {
                            "code": v.code,
                            "level": v.level,
                            "type": v.type,
                            "is_known": _is_known(v.code),
                        }
                        for v in (
                            list(disclosure.blockers) + list(disclosure.disclosures)
                            if disclosure
                            else []
                        )
                    ],
                    "channels": [
                        {
                            "delivery_type": row.snapshot.delivery_type,
                            "gap": str(row.gap),
                            "verdict": row.verdict,
                            "reason": row.reason,
                        }
                        for row in channels
                    ],
                },
            )

        def _receipt_line(receipt: Any, fallback_status: str) -> str:
            return _sse_line(
                "receipt",
                {
                    **base,
                    "status": receipt.status if receipt else fallback_status,
                    "reason": receipt.reason if receipt else None,
                    # G10 (claim 4): expected against actual, and the
                    # outcome as the receipt's own typed fields.
                    "expected_delta": (
                        str(receipt.expected_delta)
                        if receipt and receipt.expected_delta is not None
                        else None
                    ),
                    "verified": bool(receipt and receipt.verified),
                    "kind": receipt.kind if receipt else None,
                    "actual_delta": (
                        str(receipt.actual_delta)
                        if receipt and receipt.actual_delta is not None
                        else None
                    ),
                    # A verified write is not a recovered cart: a live run
                    # produced a correct write that left the guest 2.98
                    # short of the threshold. The client is told which of
                    # the two it got.
                    "blocker_cleared": bool(receipt and receipt.blocker_cleared),
                    "remaining_gap": (
                        str(receipt.remaining_gap)
                        if receipt and receipt.remaining_gap is not None
                        else None
                    ),
                },
            )

        def _options_line(candidates: Any) -> str:
            # G8 (D51): `kind`/`compensates_action_id` tell the client
            # whether this is the ordinary "add" screen or the "undo what
            # we just added" screen -- a compensation candidate's own
            # `kind` is never inferred client-side from anything else.
            return _sse_line(
                "options",
                {
                    **base,
                    "candidates": [
                        {
                            "action_id": p.action_id,
                            "product_name": p.product_name,
                            "quantity": str(p.quantity),
                            "expected_delta": str(p.expected_delta),
                            "guest_text_uk": p.guest_text_uk,
                            "kind": p.kind,
                            "compensates_action_id": p.compensates_action_id,
                            # G10 (claim 3): the hash the guard will bind
                            # to, computed here with the guard's own
                            # canonicalizer -- state holds no such field.
                            "args_hash": compute_args_hash(p.canonical_args),
                            "tool_name": p.tool_name,
                            # Evidence without `product_id`: the jury needs
                            # the price, its source and its age, not an id.
                            "evidence": [
                                {
                                    "price": str(e.price),
                                    "availability": e.availability,
                                    "source_tool": e.source_tool,
                                    "captured_at": e.captured_at.isoformat(),
                                }
                                for e in p.evidence
                            ],
                        }
                        for p in candidates
                    ],
                },
            )

        emitted_receipt = False
        if should_advance:
            # G7 (D-G7-03): the diagnosis frame needs BOTH `diagnose`'s
            # own output (diagnosis, disclosure) and `compare_channels`'s
            # (channel_comparison) -- two separate node chunks in
            # `stream_mode="updates"`, never a merged state at either
            # point. Held here until both have arrived, then emitted once
            # on the LATER (`compare_channels`) chunk -- never on
            # `diagnose` alone, which is the exact bug an adversarial
            # audit of this stage's own plan caught: emitting on
            # `diagnose` shipped `channels: []` on every live run, while
            # only the (never-advancing) replay branch below -- which
            # reads the merged checkpoint -- would have shown it working.
            pending_diagnosis: Dict[str, Any] = {}
            cart_seen: Any = existing_state.get("cart") if existing_state else None
            async for chunk in graph.astream(
                resume_input, config, stream_mode="updates"
            ):
                for node_name, partial in chunk.items():
                    if node_name == "__interrupt__":
                        continue
                    # G10 (A-G10-01): the stage frame reads NOTHING from
                    # `partial`, which is why it may sit before the falsy
                    # guard below -- a node that ran but updated no channel
                    # still belongs in the feed, and nothing here can hit
                    # the `None.get()` the guard exists for.
                    yield _sse_line(
                        "stage",
                        {
                            **base,
                            "node": node_name,
                            "io": NODE_IO.get(node_name, "pure"),
                            "usage": _spend(),
                        },
                    )
                    # A node that updates no channel arrives here as
                    # `{node_name: None}` (measured live at G7, where it
                    # crashed the stream with AttributeError AFTER the
                    # write had landed and the receipt had been persisted,
                    # so the guest saw a 500 instead of their own receipt).
                    # No node returns `{}` today; the guard stays.
                    if not partial:
                        continue
                    if partial.get("cart") is not None:
                        cart_seen = partial["cart"]
                    if node_name == "diagnose" and partial.get("diagnosis") is not None:
                        pending_diagnosis["diagnosis"] = partial["diagnosis"]
                        pending_diagnosis["disclosure"] = partial.get("disclosure")
                    if (
                        node_name == "compare_channels"
                        and "diagnosis" in pending_diagnosis
                    ):
                        yield _diagnosis_line(
                            pending_diagnosis["diagnosis"],
                            pending_diagnosis["disclosure"],
                            partial.get("channel_comparison") or [],
                            cart_seen,
                        )
                    # G8 (D51): the compensation offer arrives on
                    # `persist_receipt`'s own chunk, not `explain` --
                    # `explain` is not on the compensation path at all.
                    # Emitting from any node chunk that carries candidates
                    # covers both without naming a second node explicitly.
                    if partial.get("candidates"):
                        yield _options_line(partial["candidates"])
                    if partial.get("receipt") is not None:
                        # Emitted per node, not only from the final state:
                        # a session may run more than one consent+write
                        # round, and every round's receipt belongs to the
                        # guest who consented to it.
                        emitted_receipt = True
                        yield _receipt_line(
                            partial["receipt"], partial.get("status", "")
                        )
                    if partial.get("status") == "aborted":
                        yield _sse_line(
                            "error", {**base, "error": partial.get("error")}
                        )
        else:
            # Replay: the same frames a first-time caller saw, rebuilt from
            # the checkpoint, so a repeated GET is informative rather than
            # silent -- and, above all, does not move the graph. The
            # checkpoint is the MERGED state, so diagnosis/disclosure/
            # channel_comparison are all present together here regardless
            # of which node last touched them.
            if existing_state.get("diagnosis") is not None:
                yield _diagnosis_line(
                    existing_state["diagnosis"],
                    existing_state.get("disclosure"),
                    existing_state.get("channel_comparison") or [],
                    existing_state.get("cart"),
                )
            # G8 (D51): a compensation offer's checkpoint still carries the
            # receipt it undoes -- replaying it here means a browser
            # refresh at the offer shows the receipt above it, the same
            # gap D42's own second-round offer had (never a declared test
            # for it either) closed for both at once.
            if existing_state.get("receipt") is not None:
                yield _receipt_line(existing_state["receipt"], status or "")
            if existing_state.get("candidates"):
                yield _options_line(existing_state["candidates"])
            if status == "aborted":
                yield _sse_line("error", {**base, "error": existing_state.get("error")})

        if usage_log:
            # Persist onto the checkpoint so the next `/events` call (the
            # write run, or a second consent round) continues the count.
            spend = _spend()
            await graph.aupdate_state(
                config,
                {"tokens_used": spend["tokens"], "llm_cost_usd": spend["cost_usd"]},
            )

        final_snapshot = await graph.aget_state(config)
        final_state = final_snapshot.values
        final_status = final_state.get("status")
        if final_status == "awaiting_consent":
            yield _sse_line("consent_required", base)
        elif final_status in ("verified", "unverified") and not emitted_receipt:
            yield _receipt_line(final_state.get("receipt"), final_status)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/session/{session_id}/consent", response_model=ConsentAckResponse)
async def submit_consent(
    session_id: str, body: ConsentRequest, request: Request
) -> ConsentAckResponse:
    """Records consent and advances the checkpoint's `consent_action_id`
    -- it does NOT run the write itself. The actual outcome (a Write Guard
    refusal, or a verified/unverified receipt) is observed by the client's
    next call to `GET /session/{id}/events`, which resumes the graph.
    """
    require_session_cookie(request, session_id)
    graph = await _get_graph(request)
    config = _config(session_id)
    snapshot = await graph.aget_state(config)
    state: RecoveryState = snapshot.values
    if not state:
        raise HTTPException(status_code=404, detail="session not found")

    proposal = next(
        (p for p in state.get("candidates", []) if p.action_id == body.action_id), None
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="no matching candidate")
    if state.get("status") != "awaiting_consent":
        raise HTTPException(status_code=409, detail="session is not awaiting consent")

    cart = state["cart"]
    if cart is None:
        raise HTTPException(status_code=409, detail="session has no cart yet")
    now = datetime.now(timezone.utc)
    # D-G5-18/T18: both hashes recomputed server-side from what the
    # session already holds -- a client-supplied hash is never accepted,
    # so tampering with one on the wire has nothing to overwrite.
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id=session_id,
        owner=state["owner"],
        cart_id=cart.cart_id,
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=now,
        expires_at=now + CONSENT_TTL,
    )
    repository.save_consent(request.app.state.repo_pool, consent)

    # The deadline is re-based here, not left as the session's original one:
    # it is an absolute timestamp, so the guest's own deliberation time runs
    # it down, and `has_write_reserve` then refuses the write for lack of a
    # read-back reserve. Recording consent IS the end of deliberation, so a
    # fresh active-execution window starts from this moment.
    await graph.aupdate_state(
        config,
        {
            "consent_action_id": proposal.action_id,
            "deadline": now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
        },
    )

    # G10 (claim 3): the binding the guard will check, as recorded -- and
    # no `cart_id` (D-G10-08).
    return ConsentAckResponse(
        action_id=proposal.action_id,
        args_hash=consent.args_hash,
        state_hash=consent.state_hash,
        expires_at=consent.expires_at.isoformat(),
    )


@router.get("/evidence")
async def evidence() -> Dict[str, Any]:
    """G10 (claims 1 and 5): what a jury may be shown -- the tracked
    metrics with `n`, interval and caveat, and the sanitised disclosure
    observation. On `router`, not `app`: anything registered after the
    root mount in `main.py` is shadowed by it."""
    return load_evidence()


# `/auth/start` and `/auth/callback` live in `oauth_routes.py` -- a real,
# separately-sized OAuth implementation (metadata discovery, PKCE, token
# exchange), not a couple of lines that belong alongside session/consent
# wiring.
