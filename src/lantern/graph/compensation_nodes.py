"""`persist_receipt`, and the compensation offer it may produce (G8,
D51). Split out of `nodes.py` (D-G8-11): `nodes.py` was already 30% past
`CLAUDE.md` section 5's ~400-line ceiling before this stage, and this
node's own logic grew materially to decide whether a just-persisted write
is compensable and, if the graph is not going to run another add round,
whether to offer to undo it.

`make_write_guard_node` and `make_write_and_readback_node` STAY in
`nodes.py` -- `call_write_tool` remains a parameter of exactly one node
factory in exactly one module (`CLAUDE.md` section 4: only one node may
call a write tool), and `test_write_node_is_only_call_site_of_write_tool.py`
was widened (D-G8-11) to scan all of `src/lantern/graph/**` in the same
commit that added this module, so a second write call site anywhere in
the package would still be caught.
"""

from datetime import datetime
from typing import Any, Callable, Dict

from src.lantern.domain.compensation import (
    build_compensation_proposal,
    receipt_is_compensable,
)
from src.lantern.domain.models import Receipt
from src.lantern.graph.nodes import Node
from src.lantern.graph.state import MAX_WRITE_ROUNDS, RecoveryState, has_write_reserve


def make_persist_receipt_node(
    save_receipt: Callable[[Receipt], None],
    now: Callable[[], datetime],
) -> Node:
    """Thin persistence step for the domain decision `WriteOutcome ->
    Receipt` (already made in `make_write_and_readback_node`), PLUS the
    decision of what happens next: another add round (D42), a
    compensation offer (D51), or simply stopping.

    G8 (D-G8-05): "after the retry budget is spent" was the first draft's
    trigger, and it was unreachable in production -- `MAX_WRITE_ROUNDS`
    rounds cost more MCP attempts than `MAX_MCP_ATTEMPTS` allows before
    the loop ever completes. The corrected condition checks the budget
    HERE, at the moment of deciding whether to offer, rather than letting
    the guard discover it later and refuse a promise this node already
    made.
    """

    def persist_receipt_node(state: RecoveryState) -> Dict[str, Any]:
        receipt = state["receipt"]
        if receipt is None:
            return {"status": "aborted", "error": "persist_receipt_node: no receipt"}
        save_receipt(receipt)

        rounds_used = state.get("write_rounds_used", 0) + 1
        compensable = list(state.get("compensable", []))
        if receipt_is_compensable(receipt):
            compensable = compensable + [receipt]
        updates: Dict[str, Any] = {
            "write_rounds_used": rounds_used,
            "compensable": compensable,
        }

        written = next(
            (p for p in state["candidates"] if p.action_id == receipt.action_id), None
        )

        # G8 (D51): a compensation is never itself compensated, and never
        # restarts the D42 add-retry loop -- it deliberately leaves the
        # cart blocked (that is the whole point of undoing our own add),
        # and that is the end of this session's write activity.
        if written is not None and written.kind == "compensate":
            return updates

        # A write can be correct and still leave the guest blocked: how
        # much a write actually moves the cart cannot be known beforehand
        # (measured live -- 96.49 advertised, 86.84 charged, 2.98 short).
        # Blocker cleared is plain success: nothing to retry, nothing to
        # offer to undo.
        if receipt.blocker_cleared:
            return updates

        # This round's own outcome is not one we understand well enough to
        # act on -- an unverified write whose reason is not one of
        # D-G8-02's two "known diff" cases. Stop, exactly as before this
        # stage: no further round, and no compensation offer either,
        # since the last thing that happened is itself unexplained.
        if state["status"] != "verified" and not receipt_is_compensable(receipt):
            return updates

        if rounds_used < MAX_WRITE_ROUNDS and has_write_reserve(state, now()):
            return {
                **updates,
                # Cleared so the next pass cannot reuse a consumed
                # consent: the guard loads consent by this id, and the
                # previous one is spent.
                "consent_action_id": None,
                "consent": None,
                "candidates": [],
                # Cleared with the consent: a receipt from the previous
                # round left in place would be re-emitted as this round's
                # outcome if the next one never reaches a write.
                "receipt": None,
                "write_response": None,
                "status": "diagnosed",
            }

        # No further add round remains -- offer to undo the most recently
        # compensable write, if any accumulated (D-G8-06: a session may
        # have run several rounds; this offers the last one).
        if compensable:
            last = compensable[-1]
            source = next(
                (p for p in state["candidates"] if p.action_id == last.action_id),
                None,
            )
            proposal = (
                build_compensation_proposal(last, source.canonical_args)
                if source is not None
                else None
            )
            if proposal is not None:
                return {
                    **updates,
                    "candidates": [proposal],
                    "consent_action_id": None,
                    "consent": None,
                    "receipt": None,
                    "write_response": None,
                    "status": "awaiting_consent",
                }

        return updates

    return persist_receipt_node


__all__ = ["make_persist_receipt_node"]
