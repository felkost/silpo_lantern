"""Go/no-go criterion 4: every fixture `scripts/generate_boundary_fixtures.py`
writes to `datasets/fixtures/{synthetic,mutated}/` validates against
`datasets/fixtures/envelope.schema.json`. `datasets/fixtures/raw/` is
excluded by design — those are pre-sanitization intermediate captures, not
envelope-wrapped, and gitignored (never reach CI).
"""

import json
from pathlib import Path

import jsonschema

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA_PATH = PROJECT_ROOT / "datasets" / "fixtures" / "envelope.schema.json"


def test_every_synthetic_and_mutated_fixture_validates() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    checked = 0
    for origin in ("synthetic", "mutated"):
        for fixture_path in (PROJECT_ROOT / "datasets" / "fixtures" / origin).glob(
            "*.json"
        ):
            envelope = json.loads(fixture_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=envelope, schema=schema)
            checked += 1
    assert (
        checked > 0
    ), "no generated fixtures found — run generate_boundary_fixtures.py"
