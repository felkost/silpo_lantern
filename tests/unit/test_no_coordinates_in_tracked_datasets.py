"""a gate test guarding against the exact leak the
design plan's own adversarial audit found in its first revision -- a
committed `Receipt.before_state`/`after_state` (full `Cart.model_dump()`
dumps, `domain/models.py`) or a raw MCP capture carries `latitude`/
`longitude`/`address`, the guest's real delivery location. `make secret-scan`
does not catch this: `scripts/secret_scan.py` matches only API-key/bearer/
secret SHAPES, not PII fields with ordinary numeric or string values.

Scoped to every tracked file under `datasets/` (`raw/` is untracked --
`.gitignore` -- so it is not walked here; that directory's whole reason to
exist is that its contents are exactly this kind of unsanitized capture).
Permanent, not scoped to one stage: nothing else in the gate stops a
future sanitized/replay fixture from acquiring the same problem.
"""

import json
from pathlib import Path
from typing import Any

from src.lantern.config import PROJECT_ROOT

DATASETS_ROOT = PROJECT_ROOT / "datasets"
FORBIDDEN_KEYS = {"latitude", "longitude", "address"}


# the two documented synthetic constants
# `scripts/record_replay_bundle.py` substitutes for a real address. A
# live-recorded replay bundle MUST carry coordinates -- the sanitizer
# strips the guest's real ones and these are restored in their place,
# because `compare_channels_node` degrades to a no-op without any -- so a
# blanket ban on the KEY makes a faithful live bundle uncommittable.
#
# Narrowed rather than exempted by directory: any other value under these
# keys still fails, anywhere under datasets/, which is what the rule was
# written to catch. A real coordinate is not this pair.
_ALLOWED_SYNTHETIC_COORDINATES = {"latitude": 50.45, "longitude": 30.52}


def _is_allowed_synthetic(key: str, value: Any) -> bool:
    if key in _ALLOWED_SYNTHETIC_COORDINATES:
        return bool(value == _ALLOWED_SYNTHETIC_COORDINATES[key])
    if key == "address":
        # Allowed only when the address is EXACTLY the synthetic pair and
        # nothing else -- a real address carries city/street/phone fields
        # alongside, and any of those makes this fail.
        return isinstance(value, dict) and value == _ALLOWED_SYNTHETIC_COORDINATES
    return False


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    """Walks a decoded JSON document for any dict key in FORBIDDEN_KEYS, at
    any nesting depth -- a coordinate pair can arrive nested inside a cart,
    a shipment, or a channel snapshot, and a shallow check would miss it."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if key in FORBIDDEN_KEYS and not _is_allowed_synthetic(key, sub):
                hits.append(f"{path}.{key}")
            hits.extend(_find_forbidden_keys(sub, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_find_forbidden_keys(item, f"{path}[{index}]"))
    return hits


def _tracked_json_files() -> list[Path]:
    # `raw/` is gitignored (see module docstring); everything else tracked
    # under datasets/ must be sanitized before it reaches this repository.
    return sorted(
        path
        for path in DATASETS_ROOT.rglob("*.json")
        if "raw" not in path.relative_to(DATASETS_ROOT).parts
    )


def test_no_tracked_dataset_file_carries_a_coordinate_or_address_key() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _tracked_json_files():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # not this test's job -- other tests validate JSON shape
        hits = _find_forbidden_keys(document)
        if hits:
            offenders[path.relative_to(PROJECT_ROOT).as_posix()] = hits

    assert offenders == {}, (
        "tracked dataset file(s) carry a coordinate/address key -- sanitize "
        f"before committing: {offenders}"
    )


# the narrowing above must not turn the rule off. These pin that
# a REAL coordinate still fails, so the allowance covers exactly the two
# documented synthetic constants and nothing else.


def test_the_documented_synthetic_pair_is_allowed() -> None:
    document = {"cart": {"address": {"latitude": 50.45, "longitude": 30.52}}}
    assert _find_forbidden_keys(document) == []


def test_a_real_looking_coordinate_still_fails() -> None:
    """The author's own delivery point, as it appeared in a live capture --
    the exact thing this rule exists to keep out of the repository."""
    document = {"cart": {"address": {"latitude": 50.7429136, "longitude": 25.3206388}}}

    hits = _find_forbidden_keys(document)

    assert hits, "a real coordinate pair was let through"


def test_an_address_carrying_anything_beyond_the_pair_still_fails() -> None:
    document = {
        "cart": {
            "address": {
                "latitude": 50.45,
                "longitude": 30.52,
                "city": "Луцьк",
                "street": "Відділення #11",
            }
        }
    }

    assert _find_forbidden_keys(document), "a real street address was let through"


def test_a_bare_latitude_with_another_value_still_fails() -> None:
    assert _find_forbidden_keys({"latitude": 49.0})
    assert _find_forbidden_keys({"longitude": 28.0})
