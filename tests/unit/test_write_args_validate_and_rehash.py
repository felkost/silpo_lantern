"""T8 and T8b, and with them criterion A3.

T8: a proposal built by the real pipeline validates against the write
tool's own `inputSchema`, taken from the recorded `tools/list` capture
rather than from a hand-written copy of it.

T8b: the exact object handed to `call_write_tool` re-hashes to the
consent's `args_hash`, including a fractional quantity. This is the
property consent binding rests on: if the bytes sent are not the bytes
hashed, `args_hash` proves nothing about what was actually called, and
every other check in the Write Guard is guarding a value with no
relationship to the write.

Both were declared at kickoff and neither was written. A3 was reported as
passing on the strength of six accepted live writes -- which show the
server tolerated the arguments, not that they match what the guest
approved. Found by an adversarial audit before merge.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import jsonschema

from src.lantern.config import PROJECT_ROOT
from src.lantern.domain.action_proposal_builder import build_action_proposals
from src.lantern.domain.consent_hash import canonical_json, compute_args_hash
from src.lantern.domain.evidence_gate import (
    gate_candidates,
    raw_candidates_from_find_products_batch,
)
from src.lantern.domain.models import Cart
from src.lantern.graph.nodes import make_write_and_readback_node
from src.lantern.memory.repository import IdempotencyState
from src.lantern.policies.loader import load_registry

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
_TOOLS = PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
_WRITE_TOOL = "silpo_add_or_update_cart_products"

# Shaped like the live server's own ids, not like readable placeholders:
# the schema's `pattern` requires a UUID whose version nibble is 1-8 and
# whose variant nibble is 8/9/a/b, which `11111111-...-1111` fails. A test
# using a placeholder id would validate a payload the real server rejects.
_CART_ID = "4e83e418-a6b1-4187-b961-f8c9fb4ba2f5"
_PRODUCT_ID = "1ed3b23b-68d2-62b0-9c49-19831a0576fe"
_COMPANY_ID = "1ec88c5d-a050-669c-8467-570a157f3e31"
_BRANCH_ID = "1ee7fab3-7713-6a0c-b802-8d149aac137a"


def _write_tool_input_schema() -> Dict[str, Any]:
    envelope = json.loads(_TOOLS.read_text(encoding="utf-8"))
    for tool in envelope["payload"]["tools"]:
        if tool["name"] == _WRITE_TOOL:
            schema: Dict[str, Any] = tool["inputSchema"]
            return schema
    raise AssertionError(f"{_WRITE_TOOL} absent from the recorded tools/list")


def _response(
    price: float, *, weighted: bool = False, step: float = 1
) -> Dict[str, Any]:
    return {
        "queries": [
            {
                "query": "milk",
                "products": [
                    {
                        "id": _PRODUCT_ID,
                        "name": "Молоко «Галичина» 2,5%",
                        "slug": "moloko-halychyna",
                        "price": price,
                        "stock": 600,
                        "weighted": weighted,
                        "step": step,
                        "available": True,
                        "companyId": _COMPANY_ID,
                        "branchId": _BRANCH_ID,
                        "externalProductId": 795319,
                    }
                ],
            }
        ]
    }


def _proposal(gap: str, price: float, **kwargs: Any) -> Any:
    raw = raw_candidates_from_find_products_batch(
        call_id="call-1", response=_response(price, **kwargs), captured_at=_NOW
    )
    proposals = build_action_proposals(
        raw_candidates=raw,
        evidence=gate_candidates(raw),
        gap=Decimal(gap),
        cart=Cart(cart_id=_CART_ID, products_total=Decimal("0")),
    )
    assert proposals, "the pipeline produced no proposal to validate"
    return proposals[0]


def test_t8_canonical_args_validate_against_the_recorded_input_schema() -> None:
    jsonschema.validate(
        instance=_proposal("100.00", 39.99).canonical_args,
        schema=_write_tool_input_schema(),
    )


def test_t8_a_weighted_proposal_also_validates() -> None:
    """Weighted goods can send a fractional `quantity`; the schema's own
    `quantity: number` accepts it, but a `Decimal` would serialise as a
    JSON string and fail (an earlier decision).

    A gap of 50.00 against 199.00/kg needs 0.2513 kg, rounded up to the
    0.5 step. A larger gap would round to a whole multiple, which
    `_to_json_number` deliberately renders as an `int` — so this case has
    to be chosen, not stumbled into."""
    fractional = _proposal("50.00", 199.0, weighted=True, step=0.5)
    assert fractional.canonical_args["products"][0]["quantity"] == 0.5
    assert isinstance(fractional.canonical_args["products"][0]["quantity"], float)
    jsonschema.validate(
        instance=fractional.canonical_args, schema=_write_tool_input_schema()
    )

    whole = _proposal("100.00", 199.0, weighted=True, step=0.5)
    assert whole.canonical_args["products"][0]["quantity"] == 1
    assert isinstance(whole.canonical_args["products"][0]["quantity"], int)
    jsonschema.validate(
        instance=whole.canonical_args, schema=_write_tool_input_schema()
    )


def _capture_args_handed_to_the_write_tool(proposal: Any) -> Dict[str, Any]:
    """Runs the real write node with doubles and returns the object it
    actually passed to `call_write_tool` -- not `proposal.canonical_args`,
    which is what the hash was computed from. The whole point is to compare
    the two."""
    sent: List[Tuple[str, Dict[str, Any]]] = []

    def call_write_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        sent.append((tool_name, args))
        return {"success": True, "summary": "", "products": []}

    def claim_and_consume(
        owner: str, cart_id: str, action_id: str, args_hash: str
    ) -> Tuple[bool, IdempotencyState]:
        return True, "in_flight"

    def mark_action(
        owner: str, cart_id: str, action_id: str, state: IdempotencyState
    ) -> None:
        return None

    from src.lantern.domain.consent_hash import compute_state_hash
    from src.lantern.domain.models import ConsentRecord

    cart = Cart(cart_id=_CART_ID, products_total=Decimal("0"))
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-1",
        cart_id=_CART_ID,
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=_NOW,
        expires_at=_NOW,
    )
    node = make_write_and_readback_node(
        call_write_tool,
        lambda cart_id: {"cart": {"id": _CART_ID, "calculation": {"productsTotal": 0}}},
        claim_and_consume,
        mark_action,
        lambda: _NOW,
        load_registry(),
    )
    node(
        {
            "session_id": "s1",
            "trace_id": "t1",
            "owner": "owner-1",
            "cart": cart,
            "consent": consent,
            "candidates": [proposal],
            "diagnosis": None,
            "mcp_attempts_used": 0,
        }
    )
    assert len(sent) == 1, "expected exactly one write call"
    assert sent[0][0] == _WRITE_TOOL
    return sent[0][1]


def test_t8b_the_bytes_sent_rehash_to_the_consented_args_hash() -> None:
    proposal = _proposal("100.00", 39.99)
    consented_hash = compute_args_hash(proposal.canonical_args)

    sent = _capture_args_handed_to_the_write_tool(proposal)

    assert compute_args_hash(sent) == consented_hash
    # Stronger than hash equality, and the reason the hash holds: the
    # canonical bytes themselves are identical, so this cannot pass by a
    # collision or by both sides being canonicalised into the same summary.
    assert canonical_json(sent) == canonical_json(proposal.canonical_args)


def test_t8b_holds_for_a_fractional_quantity() -> None:
    """The spec named this case specifically. A weighted product's
    quantity is a `float` on the wire; `canonical_json` renders a
    `Decimal` as a JSON *string*, so a quantity that stayed `Decimal`
    would hash to something the sent bytes could never reproduce."""
    proposal = _proposal("50.00", 199.0, weighted=True, step=0.5)
    assert proposal.canonical_args["products"][0]["quantity"] == 0.5

    sent = _capture_args_handed_to_the_write_tool(proposal)

    assert compute_args_hash(sent) == compute_args_hash(proposal.canonical_args)
    assert canonical_json(sent) == canonical_json(proposal.canonical_args)
