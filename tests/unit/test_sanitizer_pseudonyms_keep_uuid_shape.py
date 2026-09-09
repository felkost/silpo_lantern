"""G9 (1.4): the sanitizer pseudonymises stable identifiers (`id`,
`productId`, `companyId`, `branchId`, `shoppingCartId`) so a fixture never
carries a real catalogue or account id. It emitted plain counters --
`test_id_005`, `test_company_006` -- which are not UUID-shaped.

`domain/evidence_gate.gate_candidates` requires `product_uuid`,
`company_id` and `branch_id` to be UUID-shaped (D-G5-03: they are the
three arguments the write tool's own inputSchema demands per product). So
every candidate in a SANITIZED bundle was rejected by the Evidence Gate on
replay, and the graph reached `no_action_available` with no receipts --
a bundle that cannot pass its own gate.

Found while synthesizing GD-03's bundle offline, which is exactly where it
was cheapest to find: the same defect would have surfaced during G9.1's
LIVE recording, after the live LLM and MCP spend, on a bundle that could
never replay.

The fix keeps both properties: a UUID-shaped original gets a UUID-shaped
pseudonym (obviously synthetic, deterministic, no real id published); a
non-UUID original keeps the old readable `test_*_NNN` form.
"""

import re

from src.lantern.mcp.sanitizer import sanitize_payload

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_REAL_PRODUCT_UUID = "1ede60fb-490a-6f08-96a3-65dcdf5fb860"
_REAL_COMPANY_UUID = "1ec88c5d-a050-669c-8467-570a157f3e31"


def test_a_uuid_shaped_id_gets_a_uuid_shaped_pseudonym() -> None:
    out = sanitize_payload(
        {
            "id": _REAL_PRODUCT_UUID,
            "companyId": _REAL_COMPANY_UUID,
        }
    )

    assert out["id"] != _REAL_PRODUCT_UUID, "the real id must not survive"
    assert out["companyId"] != _REAL_COMPANY_UUID
    assert _UUID_RE.match(out["id"]), (
        f"pseudonym {out['id']!r} is not UUID-shaped -- the Evidence Gate "
        "rejects it, so the bundle cannot pass its own gate on replay"
    )
    assert _UUID_RE.match(out["companyId"]), out["companyId"]


def test_a_non_uuid_id_keeps_the_readable_pseudonym_form() -> None:
    """A cart id like "cart-1" was never UUID-shaped and nothing requires
    it to be -- keep the readable form, which is easier to follow when
    eyeballing a fixture."""
    out = sanitize_payload({"shoppingCartId": "cart-1"})

    assert out["shoppingCartId"].startswith("test_cart")
    assert not _UUID_RE.match(out["shoppingCartId"])


def test_referential_integrity_survives_the_uuid_form() -> None:
    """The same original id appearing twice must still land on the same
    pseudonym -- that is the whole reason ids are pseudonymised rather
    than dropped."""
    aliases: dict = {}
    first = sanitize_payload({"productId": _REAL_PRODUCT_UUID}, aliases=aliases)
    second = sanitize_payload(
        {"validations": [], "productId": _REAL_PRODUCT_UUID}, aliases=aliases
    )

    assert first["productId"] == second["productId"]


def test_two_different_uuids_get_two_different_pseudonyms() -> None:
    out = sanitize_payload(
        {"productId": _REAL_PRODUCT_UUID, "companyId": _REAL_COMPANY_UUID}
    )
    assert out["productId"] != out["companyId"]
