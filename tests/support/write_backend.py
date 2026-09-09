"""G9 (G9.3): a parametrized fake write backend for `fake_backend`-mode
golden cases (GD-11..15, the safety slice) -- genuinely extracted from
`tests/unit/test_write_path_interrupt_and_resume.py`'s own
`_FakeWriteBackend`/`_build_graph`, not merely relocated: that original is
hardcoded to one cart, one product name, one price. `WriteBackendFixture`
parametrizes all of it, so two different golden cases can each supply
their own cart/product/price without copy-pasting the backend (T11).

The original test file is left untouched -- its own hardcoded fixture is
pinned behavior for T14/T15/T15b, not this module's concern to disturb.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ConsentRecord
from src.lantern.domain.normalizer import normalize_cart
from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.policies.loader import load_registry

TOOL_HASH = "reviewed-hash-abc"


@dataclass(frozen=True)
class WriteBackendFixture:
    """Everything `_build_graph` needs to differ between two golden
    cases: the raw cart, the product the planner will find and propose,
    and the `find_products_batch`/`time_slots`/`delivery_types` responses
    that shape. All defaulted to the values
    `test_write_path_interrupt_and_resume.py`'s own fixture uses, so a
    caller that supplies nothing reproduces that known-good baseline."""

    raw_cart: Dict[str, Any]
    find_products_response: Dict[str, Any]
    time_slots_response: Dict[str, Any] = field(
        default_factory=lambda: {
            "slots": [
                {
                    "start": "2026-09-08T10:00:00Z",
                    "end": "2026-09-08T12:00:00Z",
                    "available": True,
                    "deliveryType": "SelfPickup",
                    "deliveryCost": 0,
                    "deliveryCostMap": [],
                    "minOrderCost": 199,
                }
            ]
        }
    )
    delivery_types_response: Dict[str, Any] = field(
        default_factory=lambda: {"success": True, "summary": "", "options": []}
    )
    product_name: str = "Молоко «Галичина» 2,5%"
    product_price: float = 39.99
    # G9: the fraction of the CATALOGUE price the cart actually applies.
    # 1.0 (the default) keeps every existing case unchanged. Lower values
    # reproduce D68's measured live effect: Silpo's cart applies a
    # loyalty-card discount of ~10% that `find_products_batch` does not
    # report, so a write lands for less than the planner predicted and a
    # single round can leave a residual gap. This is the only honest way
    # to reach a two-round scenario -- a candidate whose required
    # quantity exceeds stock is DROPPED by the proposal builder, never
    # reduced, so "not enough of one item" cannot produce a partial fix.
    applied_price_ratio: float = 1.0
    # D83: rounds (1-based) in which the write tool reports success and
    # the cart does NOT move -- the one case the server's own success flag
    # cannot rule out (CLAUDE.md's fourth invariant), and the only way to
    # reach `unverified` through a read-back that actually COMPLETED
    # rather than one that crashed.
    silent_write_rounds: Tuple[int, ...] = ()
    search_terms: Tuple[str, ...] = ("Молоко «Галичина» 2,5%",)
    now: datetime = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def default_fixture() -> WriteBackendFixture:
    """Byte-for-byte the same cart/product/response shape
    `test_write_path_interrupt_and_resume.py`'s module-level constants
    use -- the baseline every existing offline write-path test already
    trusts."""
    raw_cart: Dict[str, Any] = {
        "id": "cart-1",
        "deliveryType": "NovaPoshta",
        "calculation": {
            "productsTotal": 35.0,
            "validations": [
                {
                    "level": "error",
                    "type": "order",
                    "message": "order.cost.min",
                    "context": {"orderCostMin": 599},
                }
            ],
        },
        "shipments": [
            {
                "id": "ship-1",
                "companyId": "c1",
                "branchId": "b1",
                "products": [
                    {
                        "productId": "p1",
                        "name": "Молоко «Галичина» 2,5%",
                        "quantity": 1,
                        "price": 35.0,
                    }
                ],
            }
        ],
        "address": {"latitude": 50.45, "longitude": 30.52},
        "timeslot": {
            "start": "2026-09-08T10:00:00+00:00",
            "end": "2026-09-08T12:00:00+00:00",
        },
    }
    find_products_response = {
        "queries": [
            {
                "query": "Молоко «Галичина» 2,5%",
                "products": [
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "name": "Молоко «Галичина» 2,5%",
                        "slug": "moloko-halychyna",
                        "price": 39.99,
                        "stock": 600,
                        "weighted": False,
                        "step": 1,
                        "available": True,
                        "companyId": "22222222-2222-2222-2222-222222222222",
                        "branchId": "33333333-3333-3333-3333-333333333333",
                        "externalProductId": 795319,
                    }
                ],
            }
        ]
    }
    return WriteBackendFixture(
        raw_cart=raw_cart, find_products_response=find_products_response
    )


class FakeWriteBackend:
    """Stands in for `memory.repository` + `mcp.session` together --
    parametrized by a `WriteBackendFixture` (T11) so two different golden
    cases can exercise the same graph plumbing over different data."""

    def __init__(self, fixture: Optional[WriteBackendFixture] = None) -> None:
        self.fixture = fixture or default_fixture()
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[tuple, str] = {}
        self.receipts: list = []
        self.write_calls: list = []
        self.write_side_effect_applied = False
        self.cart_after_write = dict(self.fixture.raw_cart)
        self.crash_readback_once = False
        self._readback_crashed_already = False

    def load_consent(self, action_id: str):
        record = self.consents.get(action_id)
        if record is None:
            return None, True
        return record, record.expires_at <= self.fixture.now

    def claim_and_consume(
        self, owner: str, cart_id: str, action_id: str, args_hash: str
    ):
        key = (owner, cart_id, action_id)
        if key in self.journal:
            return False, self.journal[key]
        consent = self.consents[action_id]
        consent_object = consent.model_copy(update={"consumed_at": self.fixture.now})
        self.consents[action_id] = consent_object
        self.journal[key] = "in_flight"
        return True, "in_flight"

    def mark_action(self, owner: str, cart_id: str, action_id: str, state: str) -> None:
        self.journal[(owner, cart_id, action_id)] = state

    def save_receipt(self, receipt: Any) -> None:
        self.receipts.append(receipt)

    def tool_schema_hashes(self, tool_name: str):
        return (TOOL_HASH, TOOL_HASH, False)

    def call_write_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        product = args["products"][0]
        # G9: writes ACCUMULATE. Building from the fixture's original
        # snapshot every time made a second round REPLACE the first
        # round's line item instead of adding to it -- the read-back then
        # reported "removed line items, none were consented" for a write
        # that removed nothing. D42's second round is a real path, so the
        # cart a second write lands on is the one the first write left.
        raw_cart = (
            self.cart_after_write
            if self.write_side_effect_applied
            else self.fixture.raw_cart
        )
        self.write_calls.append((tool_name, args))
        if len(self.write_calls) in self.fixture.silent_write_rounds:
            # D83: the server says yes and the cart stays put. The write
            # is still RECORDED -- a silent write is not an absent one,
            # and the journal claim behind it is real, so the metrics'
            # denominators must keep counting it.
            self.write_side_effect_applied = True
            self.cart_after_write = raw_cart
            return {"success": True, "summary": "ok", "products": [product]}
        self.write_side_effect_applied = True
        existing_products = raw_cart["shipments"][0]["products"]
        existing_total = sum(p["price"] * p["quantity"] for p in existing_products)
        # G9: price and name come from the fixture's OWN catalogue entry
        # for the product actually written, falling back to the single
        # `product_price`/`product_name` when the catalogue has no match.
        # With several candidates in `find_products_response`, ranking
        # picks one and applying a different candidate's price makes the
        # read-back fail identity -- the receipt then reads `unverified`
        # for a write that in fact landed exactly as consented.
        written_price = self.fixture.product_price
        written_name = self.fixture.product_name
        for query in self.fixture.find_products_response.get("queries", []):
            for catalogue_item in query.get("products", []):
                if catalogue_item.get("id") == product["productId"]:
                    written_price = catalogue_item["price"]
                    written_name = catalogue_item.get("name", written_name)
        written_price = round(written_price * self.fixture.applied_price_ratio, 2)
        new_line_total = written_price * product["quantity"]
        new_products_total = round(existing_total + new_line_total, 2)
        # G9: drop the order.cost.min validation once the new total clears
        # its own threshold -- what the real server does, and without it no
        # offline scenario can ever reach `blocker_cleared: true`: the cart
        # would report a minimum-order block while already being above the
        # minimum, sending the graph into a pointless second round.
        surviving_validations = []
        for validation in raw_cart["calculation"].get("validations", []):
            threshold = (validation.get("context") or {}).get("orderCostMin")
            clears = (
                validation.get("message") == "order.cost.min"
                and threshold is not None
                and new_products_total >= threshold
            )
            if not clears:
                surviving_validations.append(validation)

        self.cart_after_write = {
            **raw_cart,
            "calculation": {
                **raw_cart["calculation"],
                "productsTotal": new_products_total,
                "validations": surviving_validations,
            },
            "shipments": [
                {
                    **raw_cart["shipments"][0],
                    "products": [
                        *existing_products,
                        {
                            "productId": product["productId"],
                            "name": written_name,
                            "quantity": product["quantity"],
                            "price": written_price,
                        },
                    ],
                }
            ],
        }
        return {"success": True, "summary": "ok", "products": [product]}

    def fetch_cart_by_id_after_write(self, cart_id: str) -> Dict[str, Any]:
        if self.crash_readback_once and not self._readback_crashed_already:
            self._readback_crashed_already = True
            raise RuntimeError("simulated process kill before read-back completes")
        return {"cart": self.cart_after_write}


def build_graph(backend: FakeWriteBackend, checkpointer: Any = None) -> Any:
    fixture = backend.fixture
    planner_call: Callable[[Any], SearchIntent] = (
        lambda state: SearchIntent(  # noqa: E731
            search_terms=list(fixture.search_terms)
        )
    )
    explainer_call: Callable[[Any], ExplainerOutput] = (  # noqa: E731
        lambda proposal: ExplainerOutput(
            action_id=proposal.action_id, guest_text_uk="Додати товар"
        )
    )
    return build_recovery_graph(
        fetch_my_cart=lambda: {"shoppingCartId": fixture.raw_cart["id"]},
        fetch_cart_by_id=lambda cart_id: (
            backend.fetch_cart_by_id_after_write(cart_id)
            if backend.write_side_effect_applied
            else {"cart": fixture.raw_cart}
        ),
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: fixture.delivery_types_response,
        fetch_time_slots=lambda branch_id, types: fixture.time_slots_response,
        fetch_find_products_batch=lambda *a, **kw: fixture.find_products_response,
        planner_call=planner_call,
        explainer_call=explainer_call,
        now=lambda: fixture.now,
        checkpointer=checkpointer,
        load_consent=backend.load_consent,
        call_write_tool=backend.call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )


def grant_matching_consent(backend: FakeWriteBackend, proposal: Any) -> None:
    """Binds consent to the cart AS IT IS NOW, not to the fixture's
    original snapshot.

    G9: after a first write the cart has moved, and a consent whose
    `state_hash` was computed against the pre-write snapshot makes the
    guard refuse D42's second round with "state_hash mismatch" -- correct
    behaviour reacting to an incorrect consent. A real `submit_consent`
    hashes whatever the cart is when the guest consents, which after one
    round is the post-write cart.
    """
    fixture = backend.fixture
    current_raw = (
        backend.cart_after_write
        if backend.write_side_effect_applied
        else fixture.raw_cart
    )
    cart = normalize_cart(current_raw)
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-1",
        cart_id=fixture.raw_cart["id"],
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=fixture.now,
        expires_at=fixture.now + timedelta(minutes=5),
    )
    backend.consents[proposal.action_id] = consent
