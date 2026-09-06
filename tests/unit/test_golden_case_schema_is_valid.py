"""The golden-case JSON Schema must be
well-formed before the first 15 cases are populated against it.
"""

import json

import jsonschema
import pytest

from src.lantern.config import PROJECT_ROOT

GOLDEN_SCHEMA_PATH = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "schema.json"


def test_schema_file_is_valid_json_schema() -> None:
    schema = json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_a_minimal_case_validates() -> None:
    schema = json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(
        {
            "case_id": "GD-01",
            "scenario": "order.cost.min blocker, gap clears under self-pickup",
            "input": {"fixture_id": "cart-blocked-min-cost"},
            "expected_outcome": {"gap": 194.11},
        },
        schema,
    )


def test_a_case_missing_input_is_rejected() -> None:
    schema = json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"case_id": "GD-01", "scenario": "x", "expected_outcome": {}}, schema
        )
