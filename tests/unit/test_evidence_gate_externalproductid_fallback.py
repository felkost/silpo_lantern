"""`find_products_batch`'s own
`outputSchema` types `externalProductId` as `number | null` (measured, not
assumed) — a real product can come back with no article code at all. This
module matches on it when present, falls back to `slug`, and drops (never
guesses) a candidate resolving to neither.
"""

from datetime import datetime, timezone

from src.lantern.domain.evidence_gate import RawCandidate, gate_candidates


def _candidate(**overrides: object) -> RawCandidate:
    defaults: dict = {
        "call_id": "call-1",
        "source_tool": "silpo_find_products_batch",
        "external_product_id": 795319,
        "slug": "moloko-halychyna",
        "name": "Молоко «Галичина» 2,5%",
        "price_raw": 39.99,
        "available_raw": True,
        "captured_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return RawCandidate(**defaults)  # type: ignore[arg-type]


def test_external_product_id_is_preferred_when_present() -> None:
    survivors = gate_candidates([_candidate()])
    assert survivors[0].product_id == "795319"


def test_falls_back_to_slug_when_external_product_id_is_null() -> None:
    survivors = gate_candidates([_candidate(external_product_id=None)])
    assert survivors[0].product_id == "moloko-halychyna"


def test_a_candidate_with_neither_id_nor_slug_is_dropped_not_guessed() -> None:
    survivors = gate_candidates([_candidate(external_product_id=None, slug="")])
    assert survivors == []
