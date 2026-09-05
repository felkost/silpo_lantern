"""DR-12 (plan section 10): re-read before write, immediate read-back after
write; a write's `success` is never treated as proof of the outcome.
Declared failing per plan section 21.3 — implemented at G5+G6 (Write Guard),
but the domain-level assertion this test protects is written now, per the
plan's TDD requirement to have all five DR tests failing before any
implementation exists.

Evidence: `[I6]` section 7a — the official write tool's response is
`{success, summary, products}` only: no totals, no validations, no
checkoutWebLink. The server itself cannot say whether a blocker cleared;
only a subsequent read proves it.
"""

import pytest


@pytest.mark.xfail(strict=True, reason="Write Guard not implemented until G5+G6")
def test_write_success_without_readback_is_unverified_not_receipt():
    from src.lantern.safety.write_guard import finalize_write_outcome  # noqa: F401

    mcp_write_response = {
        "success": True,
        "summary": "updated",
        "products": [{"productId": "abc", "quantity": 2}],
    }
    outcome = finalize_write_outcome(mcp_write_response, read_back_result=None)

    assert outcome.status == "unverified"
    assert outcome.status != "receipt"
