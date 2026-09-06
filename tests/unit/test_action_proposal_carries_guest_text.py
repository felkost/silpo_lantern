"""Found while wiring `explain_node`: `ActionProposal` had `product_name`/
`quantity`/`expected_delta` typed explicitly for the consent sentence
but nowhere to put the EXPLAINER'S OWN rendered UA sentence for
the consent screen to actually display. Added with a default so this stays
non-breaking for every existing `ActionProposal` construction in the test
suite (earlier tests never set it, and get the empty-string default).
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.lantern.domain.models import ActionProposal, EvidenceTuple


def _proposal(**overrides: object) -> ActionProposal:
    evidence = EvidenceTuple(
        product_id="1",
        price=Decimal("39.99"),
        availability=True,
        source_tool="silpo_find_products_batch",
        captured_at=datetime.now(timezone.utc),
    )
    defaults: dict = {
        "action_id": "a1",
        "tool_name": "silpo_add_or_update_cart_products",
        "product_name": "x",
        "quantity": Decimal("1"),
        "expected_delta": Decimal("39.99"),
        "canonical_args": {},
        "evidence": [evidence],
    }
    defaults.update(overrides)
    return ActionProposal(**defaults)  # type: ignore[arg-type]


def test_guest_text_uk_defaults_to_empty_string() -> None:
    proposal = _proposal()
    assert proposal.guest_text_uk == ""


def test_guest_text_uk_can_be_set_via_model_copy() -> None:
    """ActionProposal is frozen — the explainer node attaches its rendered
    sentence via model_copy(update=...), never in-place mutation."""
    proposal = _proposal()
    explained = proposal.model_copy(update={"guest_text_uk": "Додайте молоко."})
    assert explained.guest_text_uk == "Додайте молоко."
    assert proposal.guest_text_uk == ""  # original untouched
