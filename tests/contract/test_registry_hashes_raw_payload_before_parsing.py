"""`CachedTools.schema_hash` must equal `compute_schema_hash` over the raw
list `fetch()` returns — never a hash taken after
`mcp_types.Tool.model_validate` has already touched the data, which
`test_schema_hash_survives_typed_roundtrip.py` proves gives a different,
wrong answer.
"""

from typing import Any, Dict, List

from src.lantern.mcp.client import ToolRegistry, compute_schema_hash


def _list_tools_raw(*names: str) -> List[Dict[str, Any]]:
    return [{"name": name, "inputSchema": {"type": "object"}} for name in names]


def test_schema_hash_matches_compute_schema_hash_over_the_raw_fetch_return() -> None:
    raw = _list_tools_raw("silpo_get_my_shopping_cart", "silpo_get_time_slots")
    registry = ToolRegistry(fetch=lambda: raw, ttl_seconds=900, now=lambda: 0.0)

    cached = registry.get()

    assert cached.schema_hash == compute_schema_hash(raw)


def test_schema_hash_changes_when_the_raw_payload_changes() -> None:
    responses = [
        _list_tools_raw("a"),
        _list_tools_raw("a", "b"),
    ]

    def fetch() -> list:
        return responses.pop(0)

    registry = ToolRegistry(fetch=fetch, ttl_seconds=900, now=lambda: 0.0)

    first = registry.get()
    second = registry.get(force_refresh=True)

    assert first.schema_hash != second.schema_hash
