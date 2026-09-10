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
from typing import Any, Dict, List, Literal, Optional, TypedDict

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
    CartDiff,
    ConsentRecord,
    Diagnosis,
    EvidenceTuple,
    LineItem,
    PolicyEntry,
    Receipt,
    Validation,
)
from src.lantern.graph.schemas import SearchIntent

# Starting values for calibration, not yet a measured value: declared
# policy constants, revisited once live runs give real usage numbers.
MAX_CYCLES = 12
# How many consent+write rounds one session may run. A second round exists
# because the amount a write actually moves cannot be known in advance:
# measured live, the catalogue advertised 96.49 for a product the cart then
# priced at 86.84, leaving the guest 2.98 short of the threshold after a
# write that was correct in every other respect. Three is a starting value
# like the constants above, not a measured one -- each round costs a
# planner call, an explainer call and several MCP reads, and asks the guest
# to consent again.
MAX_WRITE_ROUNDS = 3
MAX_MCP_ATTEMPTS = 30
MAX_TOKENS = 60_000
ACTIVE_EXECUTION_SECONDS = 90

RecoveryStatus = Literal[
    "reading",
    "diagnosed",
    "planned",
    "awaiting_consent",
    "aborted",
    # G5+G6 additions: "consented" is set once the write guard authorizes
    # (never before -- an LLM never sets this), "written" once the write
    # call itself returns, "verified"/"unverified" once the independent
    # read-back settles the outcome (plan section 11: success from MCP is
    # never treated as proof by itself).
    "consented",
    "written",
    "verified",
    "unverified",
    # Terminal, and NOT an error: the cart is blocked by something this
    # system has no action for. Every proposal it can build closes a cost
    # gap by adding products, so a cart with no cost gap (or one where the
    # gate rejected every candidate) has nothing to consent to. Measured
    # need, from the first live run: a real cart blocked by
    # `timeslot.not_available` and `product.offer.stock.max` still reached
    # the planner, which invented three drinks that could not have cleared
    # either blocker -- and the write path would have executed one and
    # issued a `verified` receipt for it.
    "no_action_available",
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
    write_rounds_used: int
    mcp_attempts_used: int
    tokens_used: int
    # G10 (D90): priced from the same usage `tokens_used` counts; both are
    # written by `apps/api/routes.py` after each `/events` run, from the
    # provider's own usage block -- never estimated.
    llm_cost_usd: float
    deadline: datetime
    # G5+G6 additions. `consent_action_id` is the ONLY thing the API sets
    # before resuming the graph (via `graph.update_state`, never via the
    # interrupt's own resume payload -- D-G5-08 requires the guard to
    # trust nothing from the resume path). It is a bare pointer; the
    # write guard node loads the actual `ConsentRecord` from Neon by this
    # id and only then populates `consent` below for the write node to use.
    owner: str
    consent_action_id: Optional[str]
    consent: Optional[ConsentRecord]
    write_response: Optional[Dict[str, Any]]
    receipt: Optional[Receipt]
    # G8 (D51/D-G8-06): every COMPENSABLE receipt seen this session,
    # oldest first. The D42 retry branch clears `receipt` between rounds
    # so it is not re-emitted -- without a separate accumulator, only the
    # LAST write would ever be undoable, and a guest could retain up to
    # `MAX_WRITE_ROUNDS - 1` items with no offer at all.
    compensable: List[Receipt]
    # G8 (D51/D-G8-08): a refused COMPENSATION is non-terminal -- unlike
    # the add path, whose refusal stays fail-closed and permanent
    # (`submit_consent` only accepts a new consent at `awaiting_consent`,
    # and `aborted` is a dead end). Bounded to a single re-offer so a
    # persistently unrecoverable state does not loop forever.
    compensation_offers_used: int


def new_recovery_state(
    session_id: str, trace_id: str, now: datetime, owner: str = ""
) -> RecoveryState:
    """The graph's entry state. `deadline` is `now + ACTIVE_EXECUTION_SECONDS`.

    This docstring previously claimed the consent wait was excluded from
    the budget "by construction", because the interrupt pause runs no node
    and `enforce_budget` is only called from inside one. That reasoning was
    wrong and cost a live run: `deadline` is an ABSOLUTE timestamp, not an
    accumulator of node runtime, and wall-clock time passes whether or not
    code is executing. `has_write_reserve` compares a real `now` against
    that fixed point, so a guest who spends longer than
    ACTIVE_EXECUTION_SECONDS deciding can never be allowed to write --
    which is exactly what happened, as `write refused: insufficient budget
    reserve`. Only a duration-accumulating budget would have the property
    claimed here.

    The deadline is therefore re-based when consent is recorded
    (`apps/api/routes.py`), which is the moment deliberation ends and a new
    active segment begins.
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
        write_rounds_used=0,
        mcp_attempts_used=0,
        tokens_used=0,
        llm_cost_usd=0.0,
        deadline=now + timedelta(seconds=ACTIVE_EXECUTION_SECONDS),
        owner=owner,
        consent_action_id=None,
        consent=None,
        write_response=None,
        receipt=None,
        compensable=[],
        compensation_offers_used=0,
    )


def has_write_reserve(
    state: RecoveryState,
    now: datetime,
    *,
    reserve_seconds: int = 20,
    mcp_reads_needed: int = 2,
    mcp_read_timeout_seconds: int = 10,
) -> bool:
    """G5+G6 (D-G5-20): plan section 6.3 -- "before write, a reserve of
    20s and two reads must remain; otherwise do not start the write." This
    is a distinct check from `enforce_budget`: it looks *forward* at what
    the write path is about to need (the write call itself plus the
    mandatory read-back), not backward at what has already been spent.
    """
    if state["mcp_attempts_used"] + mcp_reads_needed > MAX_MCP_ATTEMPTS:
        return False
    needed = timedelta(
        seconds=reserve_seconds + mcp_reads_needed * mcp_read_timeout_seconds
    )
    return now + needed <= state["deadline"]


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
    # G5+G6 additions -- without these, the checkpointer's default
    # serializer degrades a consent/receipt/diff crossing the interrupt
    # boundary exactly as it did for ActionProposal before it was listed
    # here (measured live, see this list's own header comment).
    (ConsentRecord.__module__, ConsentRecord.__name__),
    (Receipt.__module__, Receipt.__name__),
    (CartDiff.__module__, CartDiff.__name__),
]


def recovery_state_serde() -> JsonPlusSerializer:
    """The one place `RecoveryState`'s msgpack allowlist is defined —
    `get_checkpointer` and any future direct use of LangGraph's serializer
    for this state must both go through this function, so the allowlist and
    the state shape it protects can never drift apart silently the way a
    hand-copied list would.
    """
    return JsonPlusSerializer(allowed_msgpack_modules=_RECOVERY_STATE_MSGPACK_MODULES)
