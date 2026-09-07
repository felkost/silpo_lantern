"""Graph nodes: read -> diagnose -> compare_channels -> plan ->
collect_and_gate -> rank -> explain -> awaiting_consent -> write_guard ->
write_and_readback -> persist_receipt. The three write-path nodes were
added at G5+G6; everything before `awaiting_consent` is unchanged from G4.

Every MCP/LLM call is dependency-injected as a plain `Callable` — the same
pattern `ToolRegistry(fetch=...)` already established in this codebase
(`src/lantern/mcp/client.py`) — so every node here is testable with fakes,
entirely offline, with no live MCP session or LLM client required to prove
the wiring itself (call ordering, state transitions, fail-safe exits) is
correct. The real MCP/OpenRouter adapters that produce these callables in
production are a separate, later piece — building them is not the same as
calling them, and an explicit go-ahead is required before any live LLM
call happens.

Stated honestly: `collect_options`, `evidence_gate`, and the
`ActionProposal` build step are combined into one graph node
(`collect_and_gate`) rather than three, because splitting them would need
a `RawCandidate`/`EvidenceTuple` field on `RecoveryState` purely to pass
data between two nodes — extra state-graph surface for no behavioral gain,
since nothing else ever needs to observe that intermediate value. Every
one of the three logical steps still runs, in order, and each is
independently unit-tested in its own module (`evidence_gate.py`,
`action_proposal_builder.py`) — this is a node-count implementation
choice, not a scope cut.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.lantern.domain.action_proposal_builder import build_action_proposals
from src.lantern.domain.channel_snapshot_builder import (
    AmbiguousTimeSlotDataError,
    NoTimeSlotsAvailableError,
    build_channel_snapshot_from_time_slots,
    build_item_availability_by_name,
    select_timeslot_for_find_products_batch,
)
from src.lantern.domain.diagnosis import diagnose
from src.lantern.domain.disclosure import (
    ChannelSnapshot,
    build_disclosure,
    compare_channels,
)
from src.lantern.domain.evidence_gate import (
    gate_candidates,
    raw_candidates_from_find_products_batch,
)
from src.lantern.domain.models import ConsentRecord, Receipt
from src.lantern.domain.normalizer import CartShapeError, normalize_cart
from src.lantern.domain.rank import rank_candidates
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState, has_write_reserve
from src.lantern.mcp.errors import McpAdapterError
from src.lantern.memory.repository import IdempotencyState
from src.lantern.policies.loader import PolicyRegistry
from src.lantern.safety.write_guard import authorize_write, finalize_write_outcome

# LangGraph node signature: a plain function of (RecoveryState) -> a PARTIAL
# state update dict — LangGraph merges the returned keys into the running
# state; keys the node doesn't return are left untouched (measured against
# the installed SDK, not assumed — see
# `tests/unit/test_graph_pipeline_reaches_awaiting_consent.py`).
Node = Callable[[RecoveryState], Dict[str, Any]]


def make_read_node(
    fetch_my_cart: Callable[[], Mapping[str, Any]],
    fetch_cart_by_id: Callable[[str], Mapping[str, Any]],
) -> Node:
    """`silpo_get_my_shopping_cart` -> `silpo_get_shopping_cart_by_id`. The
    first call returns no cart body (a measured finding); the second call's
    parsed response nests the cart under a `cart` key
    (`normalizer.normalize_cart`'s own documented input shape).

    `checkoutWebLink` (G5+G6, D-G5-25) is a sibling of `cart` in the raw
    response, not a field inside it, so it is merged into the dict passed
    to `normalize_cart` here rather than being silently dropped.
    """

    def read_node(state: RecoveryState) -> Dict[str, Any]:
        try:
            my_cart = fetch_my_cart()
            cart_id = my_cart["shoppingCartId"]
            full = fetch_cart_by_id(cart_id)
            cart_payload = dict(full["cart"])
            cart_payload.setdefault("checkoutWebLink", full.get("checkoutWebLink"))
            cart = normalize_cart(cart_payload)
        except (CartShapeError, KeyError) as exc:
            return {"status": "aborted", "error": f"read failed: {exc}"}
        return {"cart": cart, "mcp_attempts_used": state["mcp_attempts_used"] + 2}

    return read_node


def make_diagnose_node(registry: PolicyRegistry) -> Node:
    """`registry` is loaded once at graph-build time
    (`policies.loader.load_registry()`) and closed over here — `diagnose()`
    itself stays a pure function with no I/O of its own."""

    def diagnose_node(state: RecoveryState) -> Dict[str, Any]:
        cart = state["cart"]
        if cart is None:
            return {"status": "aborted", "error": "diagnose_node reached with no cart"}
        diagnosis = diagnose(cart, registry)
        disclosure = build_disclosure(cart, diagnosis)
        return {
            "diagnosis": diagnosis,
            "disclosure": disclosure,
            "status": "diagnosed",
        }

    return diagnose_node


def make_compare_channels_node(
    fetch_delivery_types: Callable[[float, float], Mapping[str, Any]],
    fetch_time_slots: Callable[[str, Sequence[str]], Mapping[str, Any]],
    fetch_find_products_batch: Callable[
        [str, str, str, str, Sequence[str]], Mapping[str, Any]
    ],
    now: Callable[[], datetime],
) -> Node:
    """Item availability is matched by the cart's own line-item NAMES
    (`build_item_availability_by_name`), not `externalProductId` — a real,
    measured gap found while wiring this node: the only tracked live cart
    capture has zero line items, so no confirmed relationship between the
    cart's own `productId` and `find_products_batch`'s `externalProductId`
    exists yet.

    A channel this function cannot safely build a snapshot for (no free
    slot, or slots disagreeing on `minOrderCost`) is simply excluded from
    the comparison — degraded, not a reason to abort the whole recovery;
    the channel comparison is optional disclosure, not the hero path
    itself. A cart with no coordinates at all skips this node's work
    entirely for the same reason.
    """

    def compare_channels_node(state: RecoveryState) -> Dict[str, Any]:
        cart = state["cart"]
        if cart is None:
            return {
                "status": "aborted",
                "error": "compare_channels_node reached with no cart",
            }
        if cart.latitude is None or cart.longitude is None:
            return {"channel_snapshots": [], "channel_comparison": []}

        mcp_attempts = state["mcp_attempts_used"]
        delivery_types_resp = fetch_delivery_types(cart.latitude, cart.longitude)
        mcp_attempts += 1

        line_item_names = [li.name for li in cart.products]
        snapshots: List[ChannelSnapshot] = []

        for option in delivery_types_resp.get("options", []):
            delivery_type = option["deliveryType"]
            branch_id = option.get("branchId")
            branch_is_inferred = branch_id is None
            if branch_id is None:
                # SelfPickup gives no branchId directly. Resolving a real
                # branch (silpo_list_branches) is a later refinement;
                # `branch_is_inferred=True` forces the gate to
                # `needs_check`, so an empty placeholder here is a
                # fail-safe, not a fabricated fact.
                branch_id = ""

            try:
                time_slots_resp = fetch_time_slots(branch_id, [delivery_type])
                mcp_attempts += 1
                start, end = select_timeslot_for_find_products_batch(time_slots_resp)
            except (NoTimeSlotsAvailableError, McpAdapterError):
                # A live-measured gap: an unresolved/empty branchId
                # (the SelfPickup case, and live NovaPoshta too) is
                # rejected server-side as a real MCP tool error, not an
                # empty slots list — this node's own contract is to
                # degrade that ONE channel, never abort the whole recovery
                # over it.
                continue

            item_availability = None
            if line_item_names:
                try:
                    fp_resp = fetch_find_products_batch(
                        branch_id, delivery_type, start, end, line_item_names
                    )
                except McpAdapterError:
                    # Same degrade-not-abort contract as the time-slots
                    # fetch above — a channel whose availability check
                    # fails server-side is dropped from the comparison.
                    continue
                mcp_attempts += 1
                item_availability = build_item_availability_by_name(
                    expected_names=line_item_names,
                    find_products_batch_response=fp_resp,
                    call_id=f"compare-{delivery_type}-{branch_id}",
                    captured_at=now(),
                )

            try:
                snapshot = build_channel_snapshot_from_time_slots(
                    delivery_type=delivery_type,
                    branch_id=branch_id,
                    branch_is_inferred=branch_is_inferred,
                    time_slots_response=time_slots_resp,
                    item_availability=item_availability,
                )
            except (NoTimeSlotsAvailableError, AmbiguousTimeSlotDataError):
                continue
            snapshots.append(snapshot)

        comparison = compare_channels(cart.products_total, snapshots)
        return {
            "channel_snapshots": snapshots,
            "channel_comparison": comparison,
            "mcp_attempts_used": mcp_attempts,
        }

    return compare_channels_node


def make_plan_node(planner_call: Callable[[RecoveryState], SearchIntent]) -> Node:
    """`planner_call` is the ONLY thing a production adapter around
    `ChatOpenAI`/OpenRouter plugs into — building that adapter is separate
    from calling it, and no live call happens without an explicit
    go-ahead. `SearchIntent` (`graph/schemas.py`) structurally carries no
    price/productId/availability field.
    """

    def plan_node(state: RecoveryState) -> Dict[str, Any]:
        # Every proposal this pipeline can build closes a cost gap by adding
        # products, so with no gap there is nothing to plan -- and asking the
        # planner anyway is what produced three invented drinks for a cart
        # blocked by a missing delivery slot and an out-of-stock line, on the
        # first live run. Checked before `planner_call`, not after, because
        # the call costs money and its output would be discarded.
        diagnosis = state.get("diagnosis")
        if diagnosis is None or diagnosis.gap is None:
            return {"status": "no_action_available"}

        intent = planner_call(state)
        return {"search_intent": intent, "status": "planned"}

    return plan_node


def make_collect_and_gate_node(
    fetch_find_products_batch: Callable[
        [str, str, str, str, Sequence[str]], Mapping[str, Any]
    ],
    now: Callable[[], datetime],
) -> Node:
    """`collect_options`'s live search, the Evidence Gate's type/range
    filter (`evidence_gate.gate_candidates`), and `ActionProposal`
    construction (`action_proposal_builder.build_action_proposals`) —
    combined here (see module docstring) — each already an independently
    tested pure function, called here in the one order that makes a
    hallucinated candidate structurally impossible: the planner's
    `SearchIntent` supplies only search terms, never anything
    `RawCandidate`/`EvidenceTuple` could be mistaken for.
    """

    def collect_and_gate_node(state: RecoveryState) -> Dict[str, Any]:
        cart = state["cart"]
        intent = state["search_intent"]
        if cart is None or intent is None:
            return {
                "status": "aborted",
                "error": "collect_and_gate_node missing cart or search_intent",
            }
        if cart.timeslot_start is None or cart.timeslot_end is None:
            return {
                "status": "aborted",
                "error": "collect_and_gate_node: cart has no active timeslot",
            }

        response = fetch_find_products_batch(
            cart.branch_id or "",
            cart.delivery_type or "",
            cart.timeslot_start.isoformat(),
            cart.timeslot_end.isoformat(),
            intent.search_terms,
        )
        raw_candidates = raw_candidates_from_find_products_batch(
            call_id="collect_options", response=response, captured_at=now()
        )
        evidence = gate_candidates(raw_candidates)
        # The gap, not the planner's `quantity_hint`, decides how many
        # units to propose: the amount of money a write moves is code's to
        # compute (CLAUDE.md), and a hint that always came back as 1 left
        # every proposal unable to close the gap it was answering.
        diagnosis = state["diagnosis"]
        assert diagnosis is not None and diagnosis.gap is not None
        proposals = build_action_proposals(
            raw_candidates=raw_candidates,
            evidence=evidence,
            gap=diagnosis.gap,
            cart=cart,
        )
        return {
            "candidates": proposals,
            "mcp_attempts_used": state["mcp_attempts_used"] + 1,
        }

    return collect_and_gate_node


def rank_node(state: RecoveryState) -> Dict[str, Any]:
    """Truncates to the top 3 relevant products, by `rank_candidates`'
    own minimal-topup ordering."""
    ranked = rank_candidates(state["candidates"], top_n=3)
    return {"candidates": ranked}


def make_explain_node(explainer_call: Callable[[Any], ExplainerOutput]) -> Node:
    """`explainer_call` is the production `ChatOpenAI` adapter's plug-in
    point, same caveat as `make_plan_node`. Each candidate's rendered
    sentence is attached via `model_copy` — `ActionProposal` is frozen.
    Ends this slice at `awaiting_consent`, where G4 stopped; G5+G6 resumes
    the graph past this point through `make_write_guard_node` below, after
    an `interrupt_before` pause for the guest's consent.
    """

    def explain_node(state: RecoveryState) -> Dict[str, Any]:
        # A gap can exist and still leave nothing to offer: the Evidence
        # Gate drops candidates missing write identity, over stock, or off
        # the weighted step. Announcing `awaiting_consent` with an empty
        # list asks the guest to approve nothing, and the API dutifully
        # emitted `consent_required` for it -- an empty consent screen.
        if not state["candidates"]:
            return {"status": "no_action_available"}

        explained = []
        for proposal in state["candidates"]:
            output = explainer_call(proposal)
            explained.append(
                proposal.model_copy(update={"guest_text_uk": output.guest_text_uk})
            )
        return {"candidates": explained, "status": "awaiting_consent"}

    return explain_node


def make_write_guard_node(
    load_consent: Callable[[str], Tuple[Optional[ConsentRecord], bool]],
    fetch_my_cart: Callable[[], Mapping[str, Any]],
    fetch_cart_by_id: Callable[[str], Mapping[str, Any]],
    tool_schema_hashes: Callable[[str], Tuple[str, str, bool]],
    now: Callable[[], datetime],
) -> Node:
    """The single point of write authorization (`CLAUDE.md` section 4).
    Receives NO write-tool callable at all -- it cannot perform a write
    even by mistake, only decide whether the next node may. This is the
    node `build_recovery_graph` pauses in front of via `interrupt_before`.

    `tool_schema_hashes(tool_name)` returns `(reviewed_hash, live_hash,
    is_quarantined)` for one specific tool -- a lookup, not a generic
    "call any tool" dispatcher.

    Re-reads the cart via `fetch_my_cart` (not the id already in state)
    and refuses if the current cart id differs from the one consent was
    granted against -- a stale id would otherwise still read successfully
    (e.g. after checkout opened a new cart).
    """

    def write_guard_node(state: RecoveryState) -> Dict[str, Any]:
        action_id = state["consent_action_id"]
        if action_id is None:
            return {
                "status": "aborted",
                "error": "write_guard_node: no consent_action_id set",
            }

        proposal = next(
            (p for p in state["candidates"] if p.action_id == action_id), None
        )
        if proposal is None:
            return {
                "status": "aborted",
                "error": "write_guard_node: no candidate matches consent_action_id",
            }

        consent, expired = load_consent(action_id)
        if consent is None:
            return {"status": "aborted", "error": "write_guard_node: consent not found"}

        current_time = now()
        my_cart = fetch_my_cart()
        current_cart_id = my_cart["shoppingCartId"]
        full = fetch_cart_by_id(current_cart_id)
        cart_payload = dict(full["cart"])
        cart_payload.setdefault("checkoutWebLink", full.get("checkoutWebLink"))
        re_read_cart = normalize_cart(cart_payload)

        reviewed_hash, live_hash, is_quarantined = tool_schema_hashes(
            proposal.tool_name
        )
        quarantined = frozenset({proposal.tool_name}) if is_quarantined else frozenset()

        decision = authorize_write(
            proposal=proposal,
            consent=consent,
            re_read_cart=re_read_cart,
            owner=state["owner"],
            session_id=state["session_id"],
            consent_expired=expired,
            reviewed_tool_hash=reviewed_hash,
            live_tool_hash=live_hash,
            quarantined=quarantined,
            budget_reserve_ok=has_write_reserve(state, current_time),
        )
        if not decision.authorized:
            return {"status": "aborted", "error": f"write refused: {decision.reason}"}

        return {
            "consent": consent,
            "cart": re_read_cart,
            "status": "consented",
            "mcp_attempts_used": state["mcp_attempts_used"] + 2,
        }

    return write_guard_node


def make_write_and_readback_node(
    call_write_tool: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    fetch_cart_by_id: Callable[[str], Mapping[str, Any]],
    claim_and_consume: Callable[[str, str, str, str], Tuple[bool, IdempotencyState]],
    mark_action: Callable[[str, str, str, IdempotencyState], None],
    now: Callable[[], datetime],
) -> Node:
    """The ONLY node that calls a write tool (`CLAUDE.md` section 4).
    Claims the idempotency journal row and consumes the consent in one
    transaction immediately before the call (D-G5-07b) -- measured
    (probe M2b against the installed LangGraph SDK) that
    `interrupt_before` protects the write guard node from re-execution on
    resume, but NOT this node: a crash after this node's own side effect
    causes LangGraph to re-run it from the top on the next resume.

    `claim_and_consume` returns `(just_claimed, state)` rather than a bare
    state (found while writing this node's own resume test, not assumed
    correct from the signature alone): a resumed attempt whose earlier
    run already claimed the row must NEVER call `call_write_tool` again,
    even though the stored state is still `"in_flight"` (identical to
    what a fresh claim also returns) -- only `just_claimed` distinguishes
    "you may write" from "someone already claimed this, reconcile only".

    Builds the full `Receipt` here rather than passing a separate
    `WriteOutcome` through state -- `persist_receipt_node` only persists
    what this node already decided.
    """

    def _finalize(
        state: RecoveryState,
        cart: Any,
        consent: ConsentRecord,
        product: Dict[str, Any],
        proposal: Any,
        write_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            full = fetch_cart_by_id(cart.cart_id)
            cart_payload = dict(full["cart"])
            cart_payload.setdefault("checkoutWebLink", full.get("checkoutWebLink"))
            read_back_cart: Optional[Any] = normalize_cart(cart_payload)
        except (CartShapeError, KeyError, McpAdapterError):
            read_back_cart = None

        outcome = finalize_write_outcome(
            write_response,
            read_back_result=read_back_cart,
            before=cart,
            expected_delta=proposal.expected_delta,
            expected_product_id=product["productId"],
            expected_quantity=Decimal(str(product["quantity"])),
        )
        journal_next: IdempotencyState = (
            "confirmed" if outcome.status == "receipt" else "unknown"
        )
        mark_action(state["owner"], cart.cart_id, consent.action_id, journal_next)

        receipt = Receipt(
            action_id=consent.action_id,
            session_id=state["session_id"],
            owner=state["owner"],
            before_state=cart.model_dump(mode="json"),
            after_state=(
                read_back_cart.model_dump(mode="json") if read_back_cart else {}
            ),
            verified=outcome.status == "receipt",
            status=outcome.status,
            reason=outcome.reason,
            expected_delta=proposal.expected_delta,
            actual_delta=outcome.actual_delta,
            trace_id=state["trace_id"],
            created_at=now(),
        )
        return {
            "write_response": write_response,
            "receipt": receipt,
            "status": "verified" if outcome.status == "receipt" else "unverified",
            "mcp_attempts_used": state["mcp_attempts_used"] + 1,
        }

    def write_and_readback_node(state: RecoveryState) -> Dict[str, Any]:
        consent = state["consent"]
        cart = state["cart"]
        if consent is None or cart is None:
            return {
                "status": "aborted",
                "error": "write_and_readback_node: missing consent or cart",
            }
        proposal = next(
            (p for p in state["candidates"] if p.action_id == consent.action_id), None
        )
        if proposal is None:
            return {
                "status": "aborted",
                "error": "write_and_readback_node: no matching candidate",
            }
        product = proposal.canonical_args["products"][0]

        just_claimed, journal_state = claim_and_consume(
            state["owner"], cart.cart_id, consent.action_id, consent.args_hash
        )

        if not just_claimed:
            # D-G5-07c: an earlier attempt already claimed this action —
            # this is a resume after a crash, or a genuine duplicate
            # request. NEVER write again; reconcile purely from a
            # read-back, using a synthetic "not actually called this
            # time" response so `finalize_write_outcome` never treats
            # `success` from a call that never happened as evidence.
            if journal_state == "confirmed":
                return {
                    "status": "verified",
                    "write_response": {"idempotent_replay": journal_state},
                }
            if journal_state == "failed":
                return {
                    "status": "unverified",
                    "write_response": {"idempotent_replay": journal_state},
                }
            reconcile_response = {
                "success": False,
                "summary": (
                    f"reconciling from journal state '{journal_state}', "
                    "no write issued"
                ),
                "products": [],
            }
            return _finalize(
                state, cart, consent, product, proposal, reconcile_response
            )

        try:
            write_response = call_write_tool(
                proposal.tool_name, dict(proposal.canonical_args)
            )
        except McpAdapterError as exc:
            # D-G5-07c: an exception from the write call itself means the
            # server MAY have applied it -- never assumed to have failed,
            # never retried blindly. A mandatory read-back still runs.
            write_response = {"success": False, "summary": str(exc), "products": []}

        return _finalize(state, cart, consent, product, proposal, write_response)

    return write_and_readback_node


def make_persist_receipt_node(save_receipt: Callable[[Receipt], None]) -> Node:
    """Thin persistence step: the domain decision (`WriteOutcome` ->
    `Receipt`, and the idempotency journal transition) is already made in
    `make_write_and_readback_node` -- this node's only job is writing the
    already-built `Receipt` to Neon."""

    def persist_receipt_node(state: RecoveryState) -> Dict[str, Any]:
        receipt = state["receipt"]
        if receipt is None:
            return {"status": "aborted", "error": "persist_receipt_node: no receipt"}
        save_receipt(receipt)
        return {}

    return persist_receipt_node
