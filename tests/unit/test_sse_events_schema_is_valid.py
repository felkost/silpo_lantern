"""Plan section 21.2 (G1 deliverable): the SSE event envelope schema must
itself be a well-formed JSON Schema, even before G4 names concrete `event`
values.
"""

import json

import jsonschema
import pytest

from src.lantern.config import PROJECT_ROOT

SSE_SCHEMA_PATH = PROJECT_ROOT / "apps" / "api" / "sse-events.schema.json"


def test_schema_file_is_valid_json_schema() -> None:
    schema = json.loads(SSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_a_minimal_event_validates() -> None:
    schema = json.loads(SSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate({"event": "diagnose", "data": {}}, schema)


def test_an_event_missing_data_is_rejected() -> None:
    schema = json.loads(SSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "diagnose"}, schema)
