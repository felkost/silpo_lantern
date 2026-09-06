"""`RecoveryState`: the LangGraph `StateGraph`'s shared state for the
read → diagnose → plan → rank slice. A later stage extends this for
consent/write; this stage does not pre-build fields nothing here yet
produces (`ChannelSnapshot.item_availability`'s producer, consent binding,
etc. stay their own stage's job).

Budget enforcement: the envelope is up to 12 agent cycles, 30 MCP
attempts, 60,000 total input/output tokens, and 90s of active execution per
segment. `enforce_budget` is the one function every budget-consuming node
calls after doing its work; exhausting any one dimension transitions the
state to `aborted` with a named reason, never an unbounded retry loop.
"""

from datetime import datetime, timedelta
from typing import List, Literal, Optional, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.lantern.domain.disclosure import (
    ChannelComparisonRow,
    ChannelSnapshot,
    DisclosureReport,
)
from src.lantern.domain.models import (
    ActionProposal,
    Blocker,
    Cart,
    Diagnosis,
    EvidenceTuple,
    LineItem,
    PolicyEntry,
    Validation,
)
from src.lantern.graph.schemas import SearchIntent

# Starting values for calibration, not yet a measured value: declared
# policy constants, revisited once live runs give real usage numbers.
MAX_CYCLES = 12
MAX_MCP_ATTEMPTS = 30
MAX_TOKENS = 60_000
ACTIVE_EXECUTION_SECONDS = 90

RecoveryStatus = Literal[
    "reading", "diagnosed", "planned", "awaiting_consent", "aborted"
]


class RecoveryState(TypedDict):
    session_id: str
    cart: Optional[Cart]
    diagnosis: Optional[Diagnosis]
    disclosure: Optional[DisclosureReport]
    channel_snapshots: List[ChannelSnapshot]
    channel_comparison: List[ChannelComparisonRow]
    search_intent: Optional[SearchIntent]
    candidates: List[ActionProposal]
    trace_id: str
    status: RecoveryStatus
    error: Optional[str]
    cycles_used: int
    mcp_attempts_used: int
    tokens_used: int
    deadline: datetime


def new_recovery_state(session_id: str, trace_id: str, now: datetime) -> RecoveryState:
    """The graph's entry state. `deadline` is `now + ACTIVE_EXECUTION_SECONDS`
    — waiting on consent is separate from active execution time, so this
    clock only ever runs during this stage's own nodes; a future
    `await_consent` interrupt is explicitly outside it, not yet relevant
    since no consent node exists this stage.
    """
    return RecoveryState(
        session_id=session_id,
        cart=None,
        diagnosis=None,
        disclosure=None,
        channel_snapshots=[],
        channel_comparison=[],
        search_intent=None,
        candidates=[],
        trace_id=trace_id,
        status="reading",
        error=None,
        cycles_used=0,
        mcp_attempts_used=0,
        tokens_used=0,
        deadline=now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
    )


def enforce_budget(state: RecoveryState, now: datetime) -> RecoveryState:
    """Returns a NEW state (never mutates `state` in place — see this
    module's own test for why: a node's behavior must depend on what this
    function returns, not on an aliasing side effect a caller might not
    expect). An already-`aborted` state stays aborted with its original
    reason; budget enforcement only ever adds a reason, never clears one.
    """
    if state["status"] == "aborted":
        return state

    reasons: List[str] = []
    if state["cycles_used"] > MAX_CYCLES:
        reasons.append(f"cycles_used {state['cycles_used']} > {MAX_CYCLES}")
    if state["mcp_attempts_used"] > MAX_MCP_ATTEMPTS:
        reasons.append(
            f"mcp_attempts_used {state['mcp_attempts_used']} > {MAX_MCP_ATTEMPTS}"
        )
    if state["tokens_used"] > MAX_TOKENS:
        reasons.append(f"tokens_used {state['tokens_used']} > {MAX_TOKENS}")
    if now > state["deadline"]:
        reasons.append(
            f"deadline {state['deadline'].isoformat()} reached at {now.isoformat()}"
        )

    if not reasons:
        return state

    return RecoveryState(**{**state, "status": "aborted", "error": "; ".join(reasons)})


# Every Pydantic model that can appear anywhere inside a `RecoveryState`
# (measured directly — a live probe against `JsonPlusSerializer`'s default
# construction showed it logs "Deserializing unregistered type ... This
# will be blocked in a future version" for `ActionProposal` today, not a
# hypothetical future problem). `ChannelSnapshot`/`ChannelComparisonRow` and
# the domain models nested inside `Cart`/`Diagnosis`/`ActionProposal` are
# listed explicitly rather than relying on `allowed_msgpack_modules`
# accepting a bare module path — that form was tried first and does not
# suppress the warning; only the (module, classname) tuple form does.
_RECOVERY_STATE_MSGPACK_MODULES = [
    (Cart.__module__, Cart.__name__),
    (LineItem.__module__, LineItem.__name__),
    (Validation.__module__, Validation.__name__),
    (Blocker.__module__, Blocker.__name__),
    (PolicyEntry.__module__, PolicyEntry.__name__),
    (Diagnosis.__module__, Diagnosis.__name__),
    (EvidenceTuple.__module__, EvidenceTuple.__name__),
    (ActionProposal.__module__, ActionProposal.__name__),
    (DisclosureReport.__module__, DisclosureReport.__name__),
    (ChannelSnapshot.__module__, ChannelSnapshot.__name__),
    (ChannelComparisonRow.__module__, ChannelComparisonRow.__name__),
    (SearchIntent.__module__, SearchIntent.__name__),
]


def recovery_state_serde() -> JsonPlusSerializer:
    """The one place `RecoveryState`'s msgpack allowlist is defined —
    `get_checkpointer` and any future direct use of LangGraph's serializer
    for this state must both go through this function, so the allowlist and
    the state shape it protects can never drift apart silently the way a
    hand-copied list would.
    """
    return JsonPlusSerializer(allowed_msgpack_modules=_RECOVERY_STATE_MSGPACK_MODULES)
