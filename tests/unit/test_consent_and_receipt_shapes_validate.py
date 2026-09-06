"""`ConsentRecord` and `Receipt` mirror the already-merged
migration columns exactly (`0003_consents.sql`, `0005_receipts.sql`) — a
model that cannot round-trip through those tables is a shape later stages
would have to break compatibility with. This checks the field-name sets, not
just that construction succeeds, so a drift in either direction is caught.
"""

from datetime import datetime, timezone

from src.lantern.domain.models import (
    ActionProposal,
    ConsentRecord,
    EvidenceTuple,
    Receipt,
)

_CONSENTS_COLUMNS = {
    "action_id",
    "session_id",
    "owner",
    "canonical_args",
    "args_hash",
    "state_hash",
    "created_at",
    "expires_at",
    "consumed_at",
}

_RECEIPTS_COLUMNS = {
    "action_id",
    "session_id",
    "owner",
    "before_state",
    "after_state",
    "verified",
    "created_at",
}


def test_consent_record_fields_match_migration_columns() -> None:
    assert set(ConsentRecord.model_fields.keys()) == _CONSENTS_COLUMNS


def test_receipt_fields_match_migration_columns() -> None:
    assert set(Receipt.model_fields.keys()) == _RECEIPTS_COLUMNS


def test_consent_record_constructs_from_shaped_data() -> None:
    now = datetime.now(timezone.utc)
    record = ConsentRecord(
        action_id="a1",
        session_id="s1",
        owner="user-hash-1",
        canonical_args={"productId": "p1", "quantity": 6, "addQuantity": False},
        args_hash="deadbeef",
        state_hash="cafebabe",
        created_at=now,
        expires_at=now,
    )
    assert record.consumed_at is None


def test_receipt_unverified_is_representable() -> None:
    now = datetime.now(timezone.utc)
    receipt = Receipt(
        action_id="a1",
        session_id="s1",
        owner="user-hash-1",
        before_state={"total": 100},
        after_state={"total": 100},
        verified=False,
        created_at=now,
    )
    assert receipt.verified is False


def test_action_proposal_carries_consent_sentence_fields() -> None:
    now = datetime.now(timezone.utc)
    proposal = ActionProposal(
        action_id="a1",
        tool_name="silpo_add_or_update_cart_products",
        product_name="Milk",
        quantity="6",
        expected_delta="39.99",
        canonical_args={"productId": "p1", "quantity": 6, "addQuantity": False},
        evidence=[
            EvidenceTuple(
                product_id="p1",
                price="39.99",
                availability=True,
                source_tool="silpo_find_products_batch",
                captured_at=now,
            )
        ],
    )
    assert proposal.product_name == "Milk"
    assert proposal.canonical_args["addQuantity"] is False
