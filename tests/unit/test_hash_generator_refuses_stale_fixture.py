"""T4 (G8 stage spec): `scripts/generate_reviewed_tool_hashes.py` used to
hardcode `tools_list_2026-09-05.json` -- running it today would silently
REVERT the reviewed baseline to the stale hashes and break every live
write with a schema-drift refusal (five tools drifted, D47). Fixed to
read the fixture named in `reviewed_tools.json`'s own `source` field, and
to refuse (non-zero exit) when that fixture's own stated
`source_schema_hash` disagrees with a freshly recomputed one -- a
tampered or corrupted fixture must not be trusted silently.
"""

import importlib
import json

import pytest

from src.lantern.config import PROJECT_ROOT

_MODULE_PATH = "scripts.generate_reviewed_tool_hashes"


def test_generator_reads_the_fixture_named_in_reviewed_tools_source() -> None:
    module = importlib.import_module(_MODULE_PATH)
    reviewed = json.loads(
        (PROJECT_ROOT / "src" / "lantern" / "mcp" / "reviewed_tools.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_path = module.fixture_path()
    assert fixture_path == PROJECT_ROOT / reviewed["source"]


def test_generator_refuses_when_the_fixtures_own_hash_disagrees(
    tmp_path, monkeypatch
) -> None:
    module = importlib.import_module(_MODULE_PATH)
    real_fixture = json.loads(
        (
            PROJECT_ROOT
            / "tests"
            / "contract"
            / "fixtures"
            / "tools_list_2026-09-07.json"
        ).read_text(encoding="utf-8")
    )
    tampered = dict(real_fixture)
    tampered["source_schema_hash"] = "0" * 64  # deliberately wrong
    tampered_path = tmp_path / "tampered_fixture.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(SystemExit):
        module.main(fixture_path_override=tampered_path)
