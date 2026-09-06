"""`compute_schema_hash` does NOT give the same result over a `Tool` list
round-tripped through the typed MCP SDK model as it does over the raw JSON
payload the fixture carries (`e2267e94...` vs. the recorded `c914be0a...`).
Root cause, isolated directly: `Tool.model_dump()` adds `_meta`/`icons`
fields the raw wire payload never had; no `model_dump` option combination
removes fields the raw JSON never had. This is why `ToolRegistry.fetch`'s
contract returns the raw tools array and hashes it BEFORE any SDK parsing
(`src/lantern/mcp/client.py::_refresh`) — never a re-serialized typed model.

This test is now a **regression guard**, not an open question: it asserts
the mismatch, so an SDK upgrade that happened to make the round-trip
lossless would be noticed (interesting, not alarming), and so anyone tempted
to "simplify" `_refresh()` back to hashing `result.tools` gets direct
evidence of why that reintroduces false-positive drift detection on every
process start.
"""

import json
from pathlib import Path

from mcp import types as mcp_types

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.client import compute_schema_hash

FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "contract" / "fixtures" / "tools_list_2026-09-05.json"
)


def _load_fixture() -> dict:
    return json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))


def test_hash_over_typed_roundtrip_diverges_from_hash_over_raw_payload() -> None:
    envelope = _load_fixture()
    tools_raw = envelope["payload"]["tools"]

    raw_hash = compute_schema_hash(tools_raw)

    parsed = [mcp_types.Tool.model_validate(t) for t in tools_raw]
    round_tripped = [
        t.model_dump(mode="json", by_alias=True, exclude_none=False) for t in parsed
    ]
    typed_hash = compute_schema_hash(round_tripped)

    assert typed_hash != raw_hash, (
        "compute_schema_hash now matches across a typed Tool round-trip — "
        "the SDK apparently stopped adding extra fields on model_dump(). If "
        "this genuinely holds, the raw-fetch design is still correct "
        "(hashing raw is never wrong), but this test's own premise needs "
        "updating rather than silently deleting the test."
    )
