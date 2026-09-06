"""The SSE event envelope schema must
itself be a well-formed JSON Schema, and validates the five concrete
`event` names plan section 1.5 declares (D-G5-21) -- not the placeholder
node-name vocabulary this file used before any route existed to emit any
of it.
"""

import json

import jsonschema
import pytest

from src.lantern.config import PROJECT_ROOT

SSE_SCHEMA_PATH = PROJECT_ROOT / "apps" / "api" / "sse-events.schema.json"


def _schema() -> dict:
    return json.loads(SSE_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_file_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(_schema())


def test_a_minimal_diagnosis_event_validates() -> None:
    jsonschema.validate(
        {
            "event": "diagnosis",
            "data": {"session_id": "s1", "trace_id": "t1", "version": {}},
        },
        _schema(),
    )


def test_an_event_missing_data_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "diagnosis"}, _schema())


def test_an_event_outside_the_declared_enum_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {
                "event": "read",  # the retired seven-name vocabulary
                "data": {"session_id": "s1", "trace_id": "t1", "version": {}},
            },
            _schema(),
        )


def test_data_missing_the_required_envelope_fields_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "diagnosis", "data": {}}, _schema())


@pytest.mark.parametrize(
    "event_name", ["diagnosis", "options", "consent_required", "receipt", "error"]
)
def test_every_declared_event_name_validates(event_name: str) -> None:
    jsonschema.validate(
        {
            "event": event_name,
            "data": {"session_id": "s1", "trace_id": "t1", "version": {}},
        },
        _schema(),
    )
