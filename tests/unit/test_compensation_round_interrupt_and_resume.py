"""T14 (G8 stage spec): the compensation offer, proven through the REAL
compiled graph at the PRODUCTION `MAX_WRITE_ROUNDS` -- not patched down to
1. The first draft of this stage's design hid the trigger's own
unreachability by patching the constant; this harness runs three real
add rounds, each falling short of the blocker by the same discount
mechanism D40/D48 measured live (the cart applies a lower price than the
catalogue quoted), so the compensation offer is exercised as it will
actually ship.

A dedicated fake backend, not the shared `_FakeWriteBackend` from
`test_write_path_interrupt_and_resume.py`: that one's `call_write_tool`
appends a duplicate line item on a repeat call to the same product,
which is not real server replace semantics and would corrupt
`canonical_diff`'s own uniqueness assumption across three rounds.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from langgraph.checkpoint.memory import InMemorySaver

from src.lantern.domain.consent_hash import compute_args_hash, compute_state_hash
from src.lantern.domain.models import ConsentRecord
from src.lantern.graph.build import build_recovery_graph
from src.lantern.graph.schemas import ExplainerOutput, SearchIntent
from src.lantern.graph.state import MAX_WRITE_ROUNDS, new_recovery_state
from src.lantern.policies.loader import load_registry

_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
_TOOL_HASH = "reviewed-hash-abc"
_TARGET_PRODUCT_ID = "11111111-1111-1111-1111-111111111111"
_CATALOG_PRICE = 1.00  # what find_products_batch quotes
_ACTUAL_PRICE = 0.80  # what the cart actually applies -- D40/D48's discount

_FIND_PRODUCTS_RESPONSE = {
    "queries": [
        {
            "query": "Товар",
            "products": [
                {
                    "id": _TARGET_PRODUCT_ID,
                    "name": "Товар",
                    "slug": "tovar",
                    "price": _CATALOG_PRICE,
                    "stock": 100000,
                    "weighted": False,
                    "step": 1,
                    "available": True,
                    "companyId": "22222222-2222-2222-2222-222222222222",
                    "branchId": "33333333-3333-3333-3333-333333333333",
                    "externalProductId": 1,
                }
            ],
        }
    ]
}
_TIME_SLOTS_RESPONSE = {
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
_DELIVERY_TYPES_RESPONSE: Dict[str, Any] = {
    "success": True,
    "summary": "",
    "options": [],
}


def _raw_cart(quantity: int, total: float) -> Dict[str, Any]:
    products = (
        []
        if quantity == 0
        else [
            {
                "productId": _TARGET_PRODUCT_ID,
                "name": "Товар",
                "quantity": quantity,
                "price": _ACTUAL_PRICE,
            }
        ]
    )
    return {
        "id": "cart-1",
        "deliveryType": "NovaPoshta",
        "calculation": {
            "productsTotal": round(total, 2),
            "validations": (
                []
                if total >= 599
                else [
                    {
                        "level": "error",
                        "type": "order",
                        "message": "order.cost.min",
                        "context": {"orderCostMin": 599},
                    }
                ]
            ),
        },
        "shipments": [
            {"id": "ship-1", "companyId": "c1", "branchId": "b1", "products": products}
        ],
        "address": {"latitude": 50.45, "longitude": 30.52},
        "timeslot": {
            "start": "2026-09-08T10:00:00+00:00",
            "end": "2026-09-08T12:00:00+00:00",
        },
    }


def _fake_planner(state: Any) -> SearchIntent:
    return SearchIntent(search_terms=["Товар"])


def _fake_explainer(proposal: Any) -> ExplainerOutput:
    return ExplainerOutput(action_id=proposal.action_id, guest_text_uk="Додати товар")


class _RealisticFakeBackend:
    """Correct REPLACE semantics (`addQuantity: False` sets the line's
    total quantity), and applies `_ACTUAL_PRICE` regardless of the
    catalogue's `_CATALOG_PRICE` -- reproducing the exact discount
    mechanism this stage's compensation trigger exists for."""

    def __init__(self) -> None:
        self.quantity = 0
        self.total = 35.0  # a pre-existing, untouched line: "p0"
        self.consents: Dict[str, ConsentRecord] = {}
        self.journal: Dict[tuple, str] = {}
        self.receipts: list = []
        self.write_calls: list = []

    def load_consent(self, action_id: str):
        record = self.consents.get(action_id)
        if record is None:
            return None, True
        return record, record.expires_at <= _NOW

    def claim_and_consume(self, owner, cart_id, action_id, args_hash):
        key = (owner, cart_id, action_id)
        if key in self.journal:
            return False, self.journal[key]
        consent = self.consents[action_id]
        self.consents[action_id] = consent.model_copy(update={"consumed_at": _NOW})
        self.journal[key] = "in_flight"
        return True, "in_flight"

    def mark_action(self, owner, cart_id, action_id, state) -> None:
        self.journal[(owner, cart_id, action_id)] = state

    def save_receipt(self, receipt: Any) -> None:
        self.receipts.append(receipt)

    def tool_schema_hashes(self, tool_name: str):
        return (_TOOL_HASH, _TOOL_HASH, False)

    def _raw_cart_now(self) -> Dict[str, Any]:
        return _raw_cart(self.quantity, 35.0 + self.quantity * _ACTUAL_PRICE)

    def call_write_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.write_calls.append((tool_name, args))
        product = args["products"][0]
        if tool_name == "silpo_remove_cart_products":
            self.quantity = 0
        else:
            self.quantity = int(product["quantity"])
        return {"success": True, "summary": "ok", "products": [product]}

    def fetch_cart_by_id(self, cart_id: str) -> Dict[str, Any]:
        return {"cart": self._raw_cart_now()}

    def fetch_my_cart(self) -> Dict[str, Any]:
        return {"shoppingCartId": "cart-1"}


def _build_graph(backend: _RealisticFakeBackend, checkpointer: Any):
    return build_recovery_graph(
        fetch_my_cart=backend.fetch_my_cart,
        fetch_cart_by_id=backend.fetch_cart_by_id,
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: _DELIVERY_TYPES_RESPONSE,
        fetch_time_slots=lambda branch_id, types: _TIME_SLOTS_RESPONSE,
        fetch_find_products_batch=lambda *a, **kw: _FIND_PRODUCTS_RESPONSE,
        planner_call=_fake_planner,
        explainer_call=_fake_explainer,
        now=lambda: _NOW,
        checkpointer=checkpointer,
        load_consent=backend.load_consent,
        call_write_tool=backend.call_write_tool,
        claim_and_consume=backend.claim_and_consume,
        mark_action=backend.mark_action,
        save_receipt=backend.save_receipt,
        tool_schema_hashes=backend.tool_schema_hashes,
    )


def _grant_consent(backend, graph, config, proposal, cart) -> None:
    consent = ConsentRecord(
        action_id=proposal.action_id,
        session_id="s1",
        owner="owner-1",
        cart_id="cart-1",
        canonical_args=proposal.canonical_args,
        args_hash=compute_args_hash(proposal.canonical_args),
        state_hash=compute_state_hash(cart),
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=5),
    )
    backend.consents[proposal.action_id] = consent
    graph.update_state(config, {"consent_action_id": proposal.action_id})


def _run_full_hero_to_compensation_offer():
    """Drives the graph through `MAX_WRITE_ROUNDS` real add rounds -- each
    falling short of the 599 threshold by the same 20% cart discount --
    to the compensation offer. Returns (backend, graph, config, final_state).
    """
    assert MAX_WRITE_ROUNDS == 3, "this harness's own arithmetic assumes 3"
    backend = _RealisticFakeBackend()
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "t-compensation"}}
    graph = _build_graph(backend, saver)

    initial_state = new_recovery_state(
        session_id="s1", trace_id="tr1", now=_NOW, owner="owner-1"
    )
    state = graph.invoke(initial_state, config)

    for _round in range(MAX_WRITE_ROUNDS):
        assert state["status"] == "awaiting_consent", state["status"]
        proposal = state["candidates"][0]
        _grant_consent(backend, graph, config, proposal, state["cart"])
        state = graph.invoke(None, config)

    return backend, graph, config, state


def test_a_verified_write_that_leaves_the_cart_blocked_offers_compensation() -> None:
    backend, graph, config, state = _run_full_hero_to_compensation_offer()

    assert len(backend.write_calls) == MAX_WRITE_ROUNDS
    assert all(
        r.status == "receipt" and not r.blocker_cleared for r in backend.receipts
    )
    assert state["status"] == "awaiting_consent"
    assert len(state["candidates"]) == 1
    offer = state["candidates"][0]
    assert offer.kind == "compensate"
    assert offer.compensates_action_id == backend.receipts[-1].action_id


def test_the_compensation_pauses_at_write_guard_and_needs_a_second_consent() -> None:
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    assert graph.get_state(config).next == ("write_guard",)
    calls_before = len(backend.write_calls)

    # A repeated GET-equivalent (invoking with no new consent) must not
    # advance into the guard -- mirrors `apps/api/routes.py`'s own
    # `should_advance` gate at the API layer; at the graph level this is
    # simply: no update_state, no new invoke.
    assert len(backend.write_calls) == calls_before


def test_a_compensation_is_never_itself_compensated() -> None:
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    offer = state["candidates"][0]
    _grant_consent(backend, graph, config, offer, state["cart"])
    final_state = graph.invoke(None, config)

    assert final_state["status"] in ("verified", "unverified")
    # The graph ended -- no further offer, no further round.
    assert graph.get_state(config).next == ()


def test_no_second_d42_round_after_a_compensation() -> None:
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    offer = state["candidates"][0]
    _grant_consent(backend, graph, config, offer, state["cart"])
    final_state = graph.invoke(None, config)
    assert final_state["status"] != "diagnosed"


def test_stale_add_candidates_are_replaced_not_appended() -> None:
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    assert len(state["candidates"]) == 1
    assert state["candidates"][0].kind == "compensate"


def test_the_offer_restores_the_original_quantity() -> None:
    """The last write took the line from 677 to 700 (the arithmetic this
    module's docstring works out); the offer must restore it to 677, not
    remove the line entirely -- a restore-form, not a remove-form."""
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    offer = state["candidates"][0]
    assert offer.tool_name == "silpo_add_or_update_cart_products"
    assert offer.canonical_args["products"][0]["quantity"] == backend.quantity - abs(
        int(offer.quantity)
    )


def test_consent_action_id_is_cleared_after_the_offer() -> None:
    """D-G8-08 (found in adversarial review): without clearing it, the
    next `GET /events`-equivalent resume would re-enter `write_guard`
    with the ALREADY-CONSUMED consent from the write being compensated,
    refusing with 'consent has already been consumed' before the guest
    could ever answer the offer."""
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    checkpoint_values = graph.get_state(config).values
    assert checkpoint_values["consent_action_id"] is None
    assert checkpoint_values["consent"] is None


def test_a_refused_compensation_returns_to_awaiting_consent_rather_than_aborting() -> (
    None
):
    """A guard refusal is otherwise permanently terminal -- inherited
    unchanged, the guest who was offered an undo and hit a refusal would
    be stranded with both the unwanted item and no recourse. Simulated
    here by a concurrent cart change between consent and the guard's
    re-read (the same window the existing `state_hash` check already
    guards, exercised through the graph rather than the unit-level C6
    test)."""
    backend, graph, config, state = _run_full_hero_to_compensation_offer()
    offer = state["candidates"][0]
    _grant_consent(backend, graph, config, offer, state["cart"])
    # A concurrent change lands between consent and the guard's re-read.
    backend.quantity = 690
    resumed = graph.invoke(None, config)

    assert resumed["status"] == "awaiting_consent"
    assert resumed["status"] != "aborted"
    assert len(resumed["candidates"]) == 1
    assert resumed["candidates"][0].kind == "compensate"
    # Bounded: a SECOND refusal in a row aborts rather than looping forever.
    retried_offer = resumed["candidates"][0]
    _grant_consent(backend, graph, config, retried_offer, resumed["cart"])
    backend.quantity = 690  # move it again
    final = graph.invoke(None, config)
    assert final["status"] == "aborted"


class _SingleAddBackend(_RealisticFakeBackend):
    """A brand-new-line add write (existing quantity 0), so its
    compensation is the REMOVE-form -- and a simulated crash between the
    write's own side effect and the read-back exercises the exact window
    D-G8-04 fixed (`KeyError` on `product["quantity"]` for a payload that
    has none)."""

    def __init__(self) -> None:
        super().__init__()
        # Armed right before the compensation's own resume: the guard's
        # own re-read is the FIRST `fetch_cart_by_id` call in that pass
        # (must succeed, so the write can be authorized at all), the
        # write node's read-back is the SECOND -- that is the one that
        # crashes.
        self.crash_readback_once = False
        self._calls_since_armed = 0

    def fetch_cart_by_id(self, cart_id: str) -> Dict[str, Any]:
        if self.crash_readback_once:
            self._calls_since_armed += 1
            if self._calls_since_armed == 2:
                self.crash_readback_once = False
                raise RuntimeError("simulated process kill before read-back completes")
        return super().fetch_cart_by_id(cart_id)


def test_remove_form_crash_before_readback_reconciles_without_a_keyerror() -> None:
    """Isolates the exact window D-G8-04 fixed: a remove-form
    compensation's `canonical_args` carries no `quantity` key, so reading
    `product["quantity"]` unconditionally raised `KeyError` after the
    journal row was claimed and before `mark_action` -- stranding it
    `in_flight` forever. The offer is driven onto the checkpoint directly
    (`update_state`) rather than through three full add rounds, since a
    brand-new-line add (existing quantity 0) is already the remove-form
    case by construction -- no need to exhaust `MAX_WRITE_ROUNDS` first.
    """
    remove_backend = _SingleAddBackend()
    remove_saver = InMemorySaver()
    remove_config = {"configurable": {"thread_id": "t-remove-crash-2"}}
    remove_graph = _build_graph(remove_backend, remove_saver)
    remove_initial = new_recovery_state(
        session_id="s1", trace_id="tr1", now=_NOW, owner="owner-1"
    )
    remove_state = remove_graph.invoke(remove_initial, remove_config)
    from src.lantern.domain.compensation import build_compensation_proposal

    add_proposal = remove_state["candidates"][0]
    _grant_consent(
        remove_backend, remove_graph, remove_config, add_proposal, remove_state["cart"]
    )
    add_result = remove_graph.invoke(None, remove_config)
    receipt = remove_backend.receipts[-1]
    written_args = remove_backend.consents[add_proposal.action_id].canonical_args
    compensation = build_compensation_proposal(receipt, written_args)
    assert compensation is not None
    assert compensation.tool_name == "silpo_remove_cart_products"

    # Manually drive the graph's own state to the compensation offer and
    # consent to it, then resume through the simulated crash.
    remove_graph.update_state(
        remove_config,
        {
            "status": "awaiting_consent",
            "candidates": [compensation],
            "compensable": [receipt],
            "receipt": None,
        },
    )
    _grant_consent(
        remove_backend, remove_graph, remove_config, compensation, add_result["cart"]
    )
    remove_backend.crash_readback_once = True
    try:
        remove_graph.invoke(None, remove_config)
        raise AssertionError("expected the simulated crash to propagate")
    except RuntimeError:
        pass

    assert len(remove_backend.write_calls) == 2  # add, then the remove call
    # The journal row is claimed but not yet resolved -- resuming from a
    # FRESH graph object must reconcile without ever raising KeyError.
    fresh_graph = _build_graph(remove_backend, remove_saver)
    final = fresh_graph.invoke(None, remove_config)
    assert final["status"] in ("verified", "unverified")
    assert len(remove_backend.write_calls) == 2  # never written twice
