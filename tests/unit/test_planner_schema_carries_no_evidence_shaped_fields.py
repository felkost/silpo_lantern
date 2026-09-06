"""The planner's structured-output
schema must have no field named or shaped like `product_id`/`price`/
`availability` — this is what makes a hallucinated `EvidenceTuple` a
STRUCTURAL impossibility rather than a convention nobody violates by
accident. Checked directly against the schema's own field set, not against
prose describing it.
"""

from src.lantern.graph.schemas import SearchIntent

_FORBIDDEN_FIELD_NAMES = {"product_id", "price", "availability", "productid"}


def test_search_intent_has_no_evidence_shaped_field_names() -> None:
    field_names = {name.lower() for name in SearchIntent.model_fields}
    overlap = field_names & _FORBIDDEN_FIELD_NAMES
    assert not overlap, (
        f"SearchIntent carries evidence-shaped field(s) {overlap} — the "
        f"planner must never be able to emit a price/productId/availability "
        f"value that could be mistaken for gate-approved evidence"
    )


def test_search_intent_requires_at_least_one_search_term() -> None:
    intent = SearchIntent(search_terms=["молоко"])
    assert intent.search_terms == ["молоко"]


def test_search_intent_rejects_an_empty_search_term_list() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchIntent(search_terms=[])
