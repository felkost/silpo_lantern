"""The SSE event envelope schema must
itself be a well-formed JSON Schema, and validates the five concrete
`event` names plan section 1.5 declares (D-G5-21) -- not the placeholder
node-name vocabulary this file used before any route existed to emit any
of it.

G7 (D-G7-03): `diagnosis` and `receipt` now have their own `data` shape
(disclosure/channel-comparison fields; blocker_cleared/remaining_gap) --
the actual, real frame `apps/api/routes.py` emits, captured verbatim
below, is what these tests validate. `make openapi` cannot show this
change (`session_events` returns a bare `StreamingResponse`, so SSE
payloads are outside the OpenAPI document entirely) -- this file is the
verification artefact instead.
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


def _diagnosis_data(**overrides: object) -> dict:
    data = {
        "session_id": "s1",
        "trace_id": "t1",
        "version": {},
        "primary_code": "order.cost.min",
        "gap": "194.11",
        "gap_is_borderline": False,
        # G10: the arithmetic's inputs and per-code `is_known` ride along.
        "products_total": "404.89",
        "cart": {
            "delivery_type": "DeliveryHome",
            "timeslot_start": None,
            "timeslot_end": None,
            "products_total": "404.89",
            "lines": [{"name": "Молоко", "quantity": "2", "price": "39.99"}],
        },
        "threshold_source": "validation_context",
        "validations": [
            {
                "code": "order.cost.min",
                "level": "error",
                "type": "cost",
                "is_known": True,
            }
        ],
        "channels": [
            {
                "delivery_type": "SelfPickup",
                "gap": "-40.27",
                "verdict": "clears_now",
                "reason": "already clears",
            }
        ],
    }
    data.update(overrides)
    return data


def _receipt_data(**overrides: object) -> dict:
    data = {
        "session_id": "s1",
        "trace_id": "t1",
        "version": {},
        "status": "receipt",
        "reason": "verified",
        "actual_delta": "39.99",
        "blocker_cleared": False,
        "remaining_gap": "2.98",
        # G10 (claim 4): expected against actual, outcome as typed fields.
        "expected_delta": "39.99",
        "verified": True,
        "kind": "add",
        "cart": None,
    }
    data.update(overrides)
    return data


def test_a_real_diagnosis_event_validates() -> None:
    """A captured `diagnosis` frame from a real run
    (apps/api/routes.py's `_diagnosis_line`) -- this is the verification
    artefact `make openapi` cannot provide for an SSE endpoint."""
    jsonschema.validate({"event": "diagnosis", "data": _diagnosis_data()}, _schema())


def test_a_diagnosis_event_missing_channels_is_rejected() -> None:
    """The exact regression an adversarial audit of the G7 plan caught:
    emitting the frame before `compare_channels` had run would ship this
    shape -- now the schema itself refuses it."""
    data = _diagnosis_data()
    del data["channels"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "diagnosis", "data": data}, _schema())


def test_a_real_receipt_event_validates() -> None:
    jsonschema.validate({"event": "receipt", "data": _receipt_data()}, _schema())


def test_a_receipt_event_missing_blocker_cleared_is_rejected() -> None:
    data = _receipt_data()
    del data["blocker_cleared"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "receipt", "data": data}, _schema())


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


@pytest.mark.parametrize("event_name", ["consent_required", "error"])
def test_every_event_name_without_its_own_shape_validates_minimally(
    event_name: str,
) -> None:
    """`diagnosis`, `receipt` and `options` have their own required-field
    branches (tested above/below); the other two still only need the
    shared envelope."""
    jsonschema.validate(
        {
            "event": event_name,
            "data": {"session_id": "s1", "trace_id": "t1", "version": {}},
        },
        _schema(),
    )


def _options_data(**overrides: object) -> dict:
    data = {
        "session_id": "s1",
        "trace_id": "t1",
        "version": {},
        "candidates": [
            {
                "action_id": "a1",
                "product_name": "Товар",
                "quantity": "1",
                "expected_delta": "86.84",
                "guest_text_uk": "Додати товар",
                "kind": "add",
                "compensates_action_id": None,
                # G10 (claim 3): the guard's hash and the evidence, no product_id.
                "args_hash": "a" * 64,
                "tool_name": "silpo_add_or_update_cart_products",
                "evidence": [
                    {
                        "price": "86.84",
                        "availability": True,
                        "source_tool": "silpo_find_products_batch",
                        "captured_at": "2026-09-07T12:00:00+00:00",
                    }
                ],
            }
        ],
    }
    data.update(overrides)
    return data


def test_a_real_options_event_validates() -> None:
    jsonschema.validate({"event": "options", "data": _options_data()}, _schema())


def test_a_compensation_candidate_validates() -> None:
    data = _options_data()
    data["candidates"][0]["kind"] = "compensate"
    data["candidates"][0]["compensates_action_id"] = "orig-1"
    jsonschema.validate({"event": "options", "data": data}, _schema())


def test_an_options_event_missing_kind_is_rejected() -> None:
    """G8 (D51): a candidate whose kind is absent could be silently
    rendered as the wrong screen -- the client must never guess."""
    data = _options_data()
    del data["candidates"][0]["kind"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "options", "data": data}, _schema())


def test_an_options_event_with_an_unknown_kind_is_rejected() -> None:
    data = _options_data()
    data["candidates"][0]["kind"] = "wipe"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"event": "options", "data": data}, _schema())


# G10 (A-G10-01): the sixth event. `stage` carries which node completed and
# what kind of I/O it does -- nothing else: no index (the graph's own paths
# regress on one), no counters (D59), no start signal.
def _stage(io: str) -> dict:
    return {
        "event": "stage",
        "data": {
            "session_id": "s1",
            "trace_id": "t1",
            "version": {},
            "node": "collect_and_gate",
            "io": io,
            "usage": {"tokens": 1100, "cost_usd": 0.001125, "ceiling_usd": 20},
        },
    }


def test_a_real_stage_event_validates() -> None:
    jsonschema.validate(_stage("mcp"), _schema())


def test_a_stage_event_with_an_unknown_io_kind_is_rejected() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_stage("network"), _schema())


def test_a_stage_event_without_a_node_is_rejected() -> None:
    frame = _stage("mcp")
    del frame["data"]["node"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(frame, _schema())
