"""`ConsentRecord` and `Receipt` mirror the already-merged migration
columns exactly (`0003_consents.sql` + `0006_consent_receipt_versioning.sql`
for consents; `0005_receipts.sql` + `0006_...` for receipts) — a model that
cannot round-trip through those tables is a shape later stages would have
to break compatibility with.

the column sets below used to be hand-typed
literals in this file -- a count or a list typed by hand is a claim like
any other, and the cheapest way to make it true is to not type it by
hand. Parsed from the migration files themselves instead, so
a future column added to the SQL without touching the model fails here
automatically, and a model field added without a migration fails here too.
"""

import re
from datetime import datetime, timezone

from src.lantern.config import PROJECT_ROOT
from src.lantern.domain.models import (
    ActionProposal,
    ConsentRecord,
    EvidenceTuple,
    Receipt,
)

_MIGRATIONS_DIR = PROJECT_ROOT / "src" / "lantern" / "memory" / "migrations"

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", re.DOTALL
)
_ADD_COLUMN_RE = re.compile(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)", re.IGNORECASE)


def _table_columns(table: str) -> set[str]:
    """Column names for `table`, unioned across every migration file that
    creates or alters it — a `CREATE TABLE` block's own column lines plus
    every `ALTER TABLE ... ADD COLUMN` naming it."""
    columns: set[str] = set()
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for match in _CREATE_TABLE_RE.finditer(text):
            if match.group(1) != table:
                continue
            for line in match.group(2).splitlines():
                line = line.strip().rstrip(",")
                if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "CHECK")):
                    continue
                name = line.split()[0]
                columns.add(name)
        for match in _ADD_COLUMN_RE.finditer(text):
            if match.group(1) == table:
                columns.add(match.group(2))
    return columns


def test_consent_record_fields_match_migration_columns() -> None:
    assert set(ConsentRecord.model_fields.keys()) == _table_columns("consents")


def test_receipt_fields_match_migration_columns() -> None:
    assert set(Receipt.model_fields.keys()) == _table_columns("receipts")


def test_consent_record_constructs_from_shaped_data() -> None:
    now = datetime.now(timezone.utc)
    record = ConsentRecord(
        action_id="a1",
        session_id="s1",
        owner="user-hash-1",
        cart_id="cart-1",
        canonical_args={"productId": "p1", "quantity": 6, "addQuantity": False},
        args_hash="deadbeef",
        state_hash="cafebabe",
        created_at=now,
        expires_at=now,
    )
    assert record.consumed_at is None
    assert record.prompt_version is None


def test_receipt_unverified_is_representable() -> None:
    now = datetime.now(timezone.utc)
    receipt = Receipt(
        action_id="a1",
        session_id="s1",
        owner="user-hash-1",
        before_state={"total": 100},
        after_state={"total": 100},
        verified=False,
        status="unverified",
        reason="read-back unreachable",
        created_at=now,
    )
    assert receipt.verified is False
    assert receipt.status == "unverified"


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
