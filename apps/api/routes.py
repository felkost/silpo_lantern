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
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from apps.api.schemas import ConsentAckResponse, ConsentRequest, CreateSessionResponse
from src.lantern.domain.consent_hash import (
    compute_args_hash,
    compute_owner,
    compute_state_hash,
)
from src.lantern.domain.models import ConsentRecord
from src.lantern.graph.state import RecoveryState, new_recovery_state
from src.lantern.mcp.session import current_token_storage
from src.lantern.mcp.session_token_storage import SessionTokenStorage
from src.lantern.memory import repository

router = APIRouter()

CONSENT_TTL = timedelta(minutes=5)  # plan section 11.1


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


def _sse_line(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/session", response_model=CreateSessionResponse)
async def create_session(request: Request) -> CreateSessionResponse:
    session_id = str(uuid.uuid4())
    thread_id = session_id
    owner = compute_owner(session_id, request.app.state.owner_secret)
    repository.create_session(request.app.state.repo_pool, session_id, thread_id, owner)
    # A brand-new session has no guest token yet, so the client's next
    # step is `/auth/start?session_id=...`, not `/events`. Returned
    # rather than left for the client to infer from a failed stream.
    return CreateSessionResponse(
        session_id=session_id,
        authorized=False,
        auth_url=f"/auth/start?session_id={session_id}",
    )


@router.get("/session/{session_id}/events")
async def session_events(session_id: str, request: Request) -> StreamingResponse:
    """Drives the graph one segment further and streams each completed
    node as one of plan section 1.5's five SSE events. Called twice by a
    real client: once right after `POST /session` (runs the read
    pipeline to its `awaiting_consent` pause), and once again after
    `POST /session/{id}/consent` (resumes into the write pipeline to a
    `receipt`/`error` outcome).
    """
    graph = await _get_graph(request)
    config = _config(session_id)

    # Bind THIS guest's own credential for the whole run. Every MCP call
    # the graph makes reads it from the context (measured to survive both
    # LangGraph's sync-node execution and the `asyncio.run` inside
    # `mcp.session.call_tool` -- pinned by
    # `tests/unit/test_session_token_contextvar_propagates.py`). Without
    # this binding every guest would silently fall back to the single
    # operator token on disk and read somebody else's cart.
    storage = SessionTokenStorage(request.app.state.repo_pool, session_id)
    if await storage.get_tokens() is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "session is not authorized yet -- send the guest to "
                f"/auth/start?session_id={session_id}"
            ),
        )
    current_token_storage.set(storage)

    snapshot = await graph.aget_state(config)
    existing_state: RecoveryState = snapshot.values

    if not existing_state:
        session_row = repository.get_session(request.app.state.repo_pool, session_id)
        if session_row is None:
            raise HTTPException(status_code=404, detail="session not found")
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

    version_tuple = _version_tuple(request)

    async def stream() -> AsyncIterator[str]:
        base = {
            "session_id": session_id,
            "trace_id": trace_id,
            "version": version_tuple,
        }

        async for chunk in graph.astream(resume_input, config, stream_mode="updates"):
            for node_name, partial in chunk.items():
                if node_name == "__interrupt__":
                    continue
                if node_name == "diagnose" and partial.get("diagnosis") is not None:
                    diagnosis = partial["diagnosis"]
                    yield _sse_line(
                        "diagnosis",
                        {
                            **base,
                            "primary_code": diagnosis.primary_code,
                            "gap": (
                                str(diagnosis.gap)
                                if diagnosis.gap is not None
                                else None
                            ),
                        },
                    )
                if node_name == "explain" and partial.get("candidates"):
                    yield _sse_line(
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
                                }
                                for p in partial["candidates"]
                            ],
                        },
                    )
                if partial.get("status") == "aborted":
                    yield _sse_line("error", {**base, "error": partial.get("error")})

        final_snapshot = await graph.aget_state(config)
        final_state = final_snapshot.values
        status = final_state.get("status")
        if status == "awaiting_consent":
            yield _sse_line("consent_required", base)
        elif status in ("verified", "unverified"):
            receipt = final_state.get("receipt")
            yield _sse_line(
                "receipt",
                {
                    **base,
                    "status": receipt.status if receipt else status,
                    "reason": receipt.reason if receipt else None,
                    "actual_delta": (
                        str(receipt.actual_delta)
                        if receipt and receipt.actual_delta is not None
                        else None
                    ),
                },
            )

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

    await graph.aupdate_state(config, {"consent_action_id": proposal.action_id})

    return ConsentAckResponse(action_id=proposal.action_id)


# `/auth/start` and `/auth/callback` live in `oauth_routes.py` -- a real,
# separately-sized OAuth implementation (metadata discovery, PKCE, token
# exchange), not a couple of lines that belong alongside session/consent
# wiring.
