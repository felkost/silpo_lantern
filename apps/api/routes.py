"""Plan section 1.5's HTTP contract: `POST /session`, `GET /session/{id}/
events` (SSE), `POST /session/{id}/consent`, `GET /auth/start`,
`GET /auth/callback`. `/health` stays in `main.py` -- it predates this
module and its own docstring's "no I/O" contract is unrelated to session
state.

`request.app.state.graph_builder` is a zero-argument callable that builds
(and caches) the production graph -- injected this way, not called
directly, so the offline test suite can substitute a fake builder via
`app.state.graph_builder = ...` and never construct a real OpenRouter
client or make a live MCP call.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from apps.api.schemas import ConsentRequest, ConsentResponse, CreateSessionResponse
from src.lantern.domain.consent_hash import (
    compute_args_hash,
    compute_owner,
    compute_state_hash,
)
from src.lantern.domain.models import ConsentRecord
from src.lantern.graph.state import RecoveryState, new_recovery_state
from src.lantern.memory import repository

router = APIRouter()

CONSENT_TTL = timedelta(minutes=5)  # plan section 11.1


def _config(thread_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _get_graph(request: Request) -> Any:
    return request.app.state.graph_builder()


def _version_tuple(request: Request) -> Dict[str, str]:
    return dict(getattr(request.app.state, "version_tuple", {}))


@router.post("/session", response_model=CreateSessionResponse)
async def create_session(request: Request) -> CreateSessionResponse:
    graph = _get_graph(request)
    session_id = str(uuid.uuid4())
    thread_id = session_id
    trace_id = str(uuid.uuid4())
    owner = compute_owner(session_id, request.app.state.owner_secret)

    repository.create_session(request.app.state.repo_pool, session_id, thread_id, owner)

    initial_state = new_recovery_state(
        session_id=session_id,
        trace_id=trace_id,
        now=datetime.now(timezone.utc),
        owner=owner,
    )
    final_state = await graph.ainvoke(initial_state, _config(thread_id))

    return CreateSessionResponse(
        session_id=session_id,
        trace_id=trace_id,
        status=final_state["status"],
        error=final_state.get("error"),
        primary_code=(
            final_state["diagnosis"].primary_code
            if final_state.get("diagnosis")
            else None
        ),
        gap=(
            str(final_state["diagnosis"].gap)
            if final_state.get("diagnosis") and final_state["diagnosis"].gap is not None
            else None
        ),
        candidates=[
            {
                "action_id": p.action_id,
                "product_name": p.product_name,
                "quantity": str(p.quantity),
                "expected_delta": str(p.expected_delta),
                "guest_text_uk": p.guest_text_uk,
            }
            for p in final_state.get("candidates", [])
        ],
    )


def _sse_line(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/session/{session_id}/events")
async def session_events(session_id: str, request: Request) -> StreamingResponse:
    """Streams the session's already-recorded outcome as SSE events --
    `diagnosis`, `options`, `consent_required`, `receipt`, or `error`
    (plan section 1.5), each carrying `session_id`/`trace_id`/the version
    tuple. Deliberately a snapshot replay, not a live per-node push: the
    graph's own read pipeline already completes synchronously inside
    `POST /session` (bounded by the plan's own 90s active-execution
    budget), so there is no separate live progress to tail by the time a
    client opens this connection.
    """
    graph = _get_graph(request)
    snapshot = await graph.aget_state(_config(session_id))
    state: RecoveryState = snapshot.values
    version_tuple = _version_tuple(request)

    async def stream() -> AsyncIterator[str]:
        base = {
            "session_id": session_id,
            "trace_id": state.get("trace_id", ""),
            "version": version_tuple,
        }
        diagnosis = state.get("diagnosis")
        if diagnosis is not None:
            yield _sse_line(
                "diagnosis",
                {
                    **base,
                    "primary_code": diagnosis.primary_code,
                    "gap": str(diagnosis.gap) if diagnosis.gap is not None else None,
                },
            )
        candidates = state.get("candidates") or []
        if candidates:
            yield _sse_line(
                "options",
                {
                    **base,
                    "candidates": [
                        {"action_id": p.action_id, "product_name": p.product_name}
                        for p in candidates
                    ],
                },
            )
        status = state.get("status")
        if status == "awaiting_consent":
            yield _sse_line("consent_required", base)
        elif status in ("verified", "unverified"):
            receipt = state.get("receipt")
            yield _sse_line(
                "receipt",
                {**base, "status": receipt.status if receipt else status},
            )
        elif status == "aborted":
            yield _sse_line("error", {**base, "error": state.get("error")})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/session/{session_id}/consent", response_model=ConsentResponse)
async def submit_consent(
    session_id: str, body: ConsentRequest, request: Request
) -> ConsentResponse:
    graph = _get_graph(request)
    snapshot = await graph.aget_state(_config(session_id))
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

    await graph.aupdate_state(
        _config(session_id), {"consent_action_id": proposal.action_id}
    )
    final_state = await graph.ainvoke(None, _config(session_id))

    if final_state["status"] == "aborted":
        # B3: the Write Guard itself refused (stale state_hash, expired
        # consent, owner/session mismatch, schema drift, ...) -- a typed
        # 422, not a 200 the client would have to inspect a status field
        # on to notice something went wrong.
        raise HTTPException(
            status_code=422, detail=final_state.get("error") or "write refused"
        )

    receipt = final_state.get("receipt")
    return ConsentResponse(
        status=final_state["status"],
        reason=receipt.reason if receipt else None,
        actual_delta=receipt.actual_delta if receipt else None,
    )


@router.get("/auth/start")
async def auth_start() -> Dict[str, str]:
    """The backend's own Silpo MCP OAuth (plan section 1.2) is a
    backend-to-server credential, obtained today by the one-time
    phone+OTP script (`scripts/silpo_mcp_login.py`) -- `CLAUDE.md`'s own
    session protocol requires that flow to never let an agent open a
    browser. This route's contract exists per plan section 1.5; making it
    actually drive the OAuth redirect is future work, not this stage's:
    no route here depends on it, and B1-B3's own criteria never exercise
    live OAuth."""
    raise HTTPException(
        status_code=501,
        detail=(
            "Not implemented this stage -- the backend's MCP OAuth token is "
            "obtained via scripts/silpo_mcp_login.py, run manually by the "
            "operator."
        ),
    )


@router.get("/auth/callback")
async def auth_callback() -> Dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented this stage")
