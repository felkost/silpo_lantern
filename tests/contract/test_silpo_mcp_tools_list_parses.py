"""Recorded contract test: the `tools/list` snapshot is copied into a
tracked fixture rather than left under a gitignored local-evidence
directory, so it does not break on a fresh clone/CI checkout. Confirms the
fixture parses into typed `Tool` objects and that this project's own hash
function reproduces the recorded `schema_hash`.
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


def test_fixture_validates_against_the_envelope_schema() -> None:
    import jsonschema

    schema = json.loads(
        (PROJECT_ROOT / "datasets" / "fixtures" / "envelope.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(_load_fixture(), schema)


def test_recomputed_schema_hash_matches_the_recorded_value() -> None:
    envelope = _load_fixture()
    tools_raw = envelope["payload"]["tools"]
    assert compute_schema_hash(tools_raw) == envelope["source_schema_hash"]


def test_every_tool_parses_into_a_typed_tool_object() -> None:
    envelope = _load_fixture()
    tools_raw = envelope["payload"]["tools"]
    parsed = [mcp_types.Tool.model_validate(t) for t in tools_raw]
    assert len(parsed) == envelope["payload"]["tool_count"]
    assert all(isinstance(t, mcp_types.Tool) for t in parsed)
