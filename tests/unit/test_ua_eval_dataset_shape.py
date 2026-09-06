"""UA-Eval mini-benchmark dataset: 25-30 domain prompts covering
validation-code explanations, numerals/sums, units/package sizes,
declension of real product names, and polite refusals. This test is the
one check standing between a hand-typed count ("25-30 prompts") and it
silently being 22 or 34.

Not a live scoring run: no LLM is called. Scoring/calibration is a
separate, later script requiring the author's explicit go-ahead before any
live call.
"""

import json
from collections import Counter

import yaml

from src.lantern.config import PROJECT_ROOT
from src.lantern.policies.loader import DEFAULT_REGISTRY_PATH

DATASET_PATH = PROJECT_ROOT / "datasets" / "ua-eval-v1.0.0" / "prompts.json"

_REQUIRED_CATEGORIES = {
    "validation_code_explanation",
    "numerals_and_sums",
    "units_and_package_size",
    "product_name_declension",
    "polite_refusal",
}


def _load() -> list:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def test_dataset_file_exists_and_parses() -> None:
    prompts = _load()
    assert isinstance(prompts, list)


def test_prompt_count_is_within_the_plan_specified_range() -> None:
    """ "25-30 доменних промптів" — checked by counting
    the actual list, not by trusting a comment."""
    prompts = _load()
    assert 25 <= len(prompts) <= 30


def test_every_prompt_has_the_required_fields() -> None:
    prompts = _load()
    for entry in prompts:
        assert entry["id"], entry
        assert entry["category"] in _REQUIRED_CATEGORIES, entry
        assert entry["prompt_uk"], entry


def test_all_five_categories_are_represented() -> None:
    prompts = _load()
    categories = {entry["category"] for entry in prompts}
    assert categories == _REQUIRED_CATEGORIES


def test_prompt_ids_are_unique() -> None:
    prompts = _load()
    ids = [entry["id"] for entry in prompts]
    duplicates = [pid for pid, count in Counter(ids).items() if count > 1]
    assert not duplicates, duplicates


def test_validation_code_prompts_cover_every_registry_entry() -> None:
    """One explanation prompt per policy-registry code, including the
    quarantined codes with no confirmed registry match — explaining an
    unregistered code honestly, without aliasing it, is itself part of the
    language task, not exempt from it."""
    prompts = _load()
    covered_codes = {
        entry["validation_code"]
        for entry in prompts
        if entry["category"] == "validation_code_explanation"
    }
    raw_registry = yaml.safe_load(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry_codes = {entry["code"] for entry in raw_registry["entries"]}
    assert covered_codes == registry_codes


def test_product_name_prompts_use_only_measured_real_names() -> None:
    """These are the only two product names this project has ever
    captured live — inventing a plausible product name is forbidden, so
    this test pins the dataset to exactly those two."""
    prompts = _load()
    real_names = {
        entry["product_name"]
        for entry in prompts
        if entry["category"] == "product_name_declension"
    }
    assert real_names == {
        # The live catalogue name is fuller than an earlier recorded text —
        # a catalogue name can drift from what an earlier decision log
        # captured; the current live value wins.
        "Молоко «Галичина» «З чистих Карпат» 2,5%",
        "Вершки «Премія»® ультрапастеризовані 15%",
    }


def test_numerals_and_sums_prompts_cover_the_ukrainian_plural_forms() -> None:
    """Ukrainian numeral agreement has three plural classes (1 / 2-4 / 5+),
    each with a different noun form (гривня/гривні/гривень) — a UA-Eval
    category that doesn't exercise all three isn't testing what it claims
    to."""
    prompts = _load()
    numeral_prompts = [p for p in prompts if p["category"] == "numerals_and_sums"]
    classes_covered = {p["numeral_class"] for p in numeral_prompts}
    assert classes_covered == {"one", "few", "many"}
