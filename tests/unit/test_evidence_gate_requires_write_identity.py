"""G5+G6 (D-G5-03): `resolve_product_id` used to fall back from
`externalProductId` to `slug` -- retired now that a live probe (P1)
confirmed `find_products_batch`'s own `id` field is a required, non-null
UUID matching the write tool's `productId` argument and the cart's own
`LineItem.product_id`. This file's substance changes accordingly: it now
tests the write-identity resolution and the accompanying
`companyId`/`branchId` requirement, not the retired fallback.
"""

from datetime import datetime, timezone

from src.lantern.domain.evidence_gate import RawCandidate, gate_candidates

_UUID_1 = "11111111-1111-1111-1111-111111111111"
_UUID_2 = "22222222-2222-2222-2222-222222222222"
_UUID_3 = "33333333-3333-3333-3333-333333333333"


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
        "product_uuid": _UUID_1,
        "company_id": _UUID_2,
        "branch_id": _UUID_3,
    }
    defaults.update(overrides)
    return RawCandidate(**defaults)  # type: ignore[arg-type]


def test_product_uuid_is_the_resolved_identity() -> None:
    survivors = gate_candidates([_candidate()])
    assert survivors[0].product_id == _UUID_1


def test_a_candidate_with_no_product_uuid_is_dropped_not_guessed() -> None:
    """The `externalProductId`/`slug` fallback this module used before
    D-G5-03 is retired: `find_products_batch`'s own `id` field is
    required and non-null, so there is no live case left where falling
    back to `slug` would ever fire -- a missing `product_uuid` is dropped,
    never approximated from a different field."""
    survivors = gate_candidates([_candidate(product_uuid=None)])
    assert survivors == []


def test_a_non_uuid_shaped_product_uuid_is_dropped() -> None:
    survivors = gate_candidates([_candidate(product_uuid="not-a-uuid")])
    assert survivors == []


def test_a_candidate_missing_company_id_is_dropped() -> None:
    survivors = gate_candidates([_candidate(company_id=None)])
    assert survivors == []


def test_a_candidate_missing_branch_id_is_dropped() -> None:
    survivors = gate_candidates([_candidate(branch_id=None)])
    assert survivors == []


def test_a_candidate_with_all_three_ids_survives() -> None:
    survivors = gate_candidates([_candidate()])
    assert len(survivors) == 1
