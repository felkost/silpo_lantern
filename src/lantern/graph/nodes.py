"""Graph nodes: read -> diagnose -> compare_channels -> plan ->
collect_and_gate -> rank -> explain -> terminal `awaiting_consent`.

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
from typing import Any, Callable, Dict, List, Mapping, Sequence

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
from src.lantern.domain.normalizer import CartShapeError, normalize_cart
from src.lantern.domain.rank import rank_candidates
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import RecoveryState
from src.lantern.mcp.errors import McpAdapterError
from src.lantern.policies.loader import PolicyRegistry

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
    """

    def read_node(state: RecoveryState) -> Dict[str, Any]:
        try:
            my_cart = fetch_my_cart()
            cart_id = my_cart["shoppingCartId"]
            full = fetch_cart_by_id(cart_id)
            cart = normalize_cart(full["cart"])
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
        proposals = build_action_proposals(
            raw_candidates=raw_candidates,
            evidence=evidence,
            quantity=intent.quantity_hint,
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
    Ends this slice at `awaiting_consent`: no node past this one exists
    this stage — the write route is a deliberate dead end.
    """

    def explain_node(state: RecoveryState) -> Dict[str, Any]:
        explained = []
        for proposal in state["candidates"]:
            output = explainer_call(proposal)
            explained.append(
                proposal.model_copy(update={"guest_text_uk": output.guest_text_uk})
            )
        return {"candidates": explained, "status": "awaiting_consent"}

    return explain_node
