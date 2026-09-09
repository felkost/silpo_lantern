"""The golden-case JSON Schema must be
well-formed before the first 15 cases are populated against it.

Amended at G9 (D60): adds `allowed_trajectories`, `allowed_tools`,
`forbidden_tools`, `rubric`, `source_id`, `pii_status`, and a `mode`
discriminator (`replay` | `fake_backend`) the runner dispatches on.
`mode`/`source_id`/`pii_status` are required on every case; the other four
are typed but optional -- not every case needs a trajectory set or a tool
allow/forbid-list (e.g. a `fake_backend` safety case has neither).
"""

import json

import jsonschema
import pytest

from src.lantern.config import PROJECT_ROOT

GOLDEN_SCHEMA_PATH = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "schema.json"


def _schema() -> dict:
    return json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))


def _minimal_case(**overrides: object) -> dict:
    case = {
        "case_id": "GD-01",
        "scenario": "order.cost.min blocker, gap clears under self-pickup",
        "input": {"fixture_id": "cart-blocked-min-cost"},
        "expected_outcome": {"gap": 194.11},
        "mode": "replay",
        "source_id": "live-recorded-2026-09-09",
        "pii_status": "sanitized",
    }
    case.update(overrides)
    return case


def test_schema_file_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(_schema())


def test_a_minimal_case_validates() -> None:
    jsonschema.validate(_minimal_case(), _schema())


def test_a_case_missing_input_is_rejected() -> None:
    case = _minimal_case()
    del case["input"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_a_case_missing_mode_is_rejected() -> None:
    case = _minimal_case()
    del case["mode"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_a_case_missing_source_id_is_rejected() -> None:
    case = _minimal_case()
    del case["source_id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_a_case_missing_pii_status_is_rejected() -> None:
    case = _minimal_case()
    del case["pii_status"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_mode_only_accepts_the_two_declared_values() -> None:
    case = _minimal_case(mode="something_else")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_pii_status_only_accepts_declared_values() -> None:
    case = _minimal_case(pii_status="maybe")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_a_case_may_omit_the_optional_evaluation_fields() -> None:
    # allowed_trajectories/allowed_tools/forbidden_tools/rubric are typed,
    # not required -- a fake_backend safety case has no trajectory set.
    jsonschema.validate(_minimal_case(mode="fake_backend"), _schema())


def test_a_case_may_carry_the_optional_evaluation_fields() -> None:
    case = _minimal_case(
        allowed_trajectories=[["read", "diagnose", "plan", "write_guard"]],
        allowed_tools=["silpo_add_or_update_cart_products"],
        forbidden_tools=["silpo_remove_cart_products"],
        rubric="the recovered cart clears the blocker within 3 rounds",
    )
    jsonschema.validate(case, _schema())


def test_allowed_trajectories_must_be_a_list_of_lists_of_strings() -> None:
    case = _minimal_case(allowed_trajectories="not-a-list")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())


def test_an_unknown_top_level_key_is_rejected() -> None:
    case = _minimal_case(unexpected_field="x")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(case, _schema())
