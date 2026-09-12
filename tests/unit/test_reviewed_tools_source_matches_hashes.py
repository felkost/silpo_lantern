"""T3: `reviewed_tools.json`'s `source`, `source_schema_hash`
and `reviewed_at` must all describe the SAME baseline as its stored
`tool_hashes`. Found stale (audit row 10 kickoff): `source` named the
2026-09-05 fixture and `source_schema_hash` was that fixture's own
whole-array hash, while all 39 stored `tool_hashes` actually matched the
2026-09-07 fixture (the live regeneration) -- a file that misdescribes
the baseline the write path is authorized against is a live hazard, not
merely an inconsistency.
"""

import json

from src.lantern.config import PROJECT_ROOT
from src.lantern.mcp.client import compute_per_tool_schema_hashes, compute_schema_hash

_REVIEWED_TOOLS_PATH = PROJECT_ROOT / "src" / "lantern" / "mcp" / "reviewed_tools.json"


def _reviewed() -> dict:
    return json.loads(_REVIEWED_TOOLS_PATH.read_text(encoding="utf-8"))


def _source_fixture_tools(reviewed: dict) -> list:
    source_path = PROJECT_ROOT / reviewed["source"]
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return payload["payload"]["tools"]


def test_source_schema_hash_matches_the_named_source_fixture() -> None:
    reviewed = _reviewed()
    tools = _source_fixture_tools(reviewed)
    assert reviewed["source_schema_hash"] == compute_schema_hash(tools)


def test_tool_hashes_match_the_named_source_fixture_not_a_different_one() -> None:
    """The stronger check: not just that SOME fixture's hashes match
    `tool_hashes`, but that the fixture named in `source` specifically
    does -- the whole point of the `source` field."""
    reviewed = _reviewed()
    tools = _source_fixture_tools(reviewed)
    recomputed = compute_per_tool_schema_hashes(tools)
    for name, stored_hash in reviewed["tool_hashes"].items():
        assert recomputed.get(name) == stored_hash, (
            f"{name}: reviewed_tools.json's tool_hashes does not match "
            f"the fixture named in its own 'source' field"
        )
