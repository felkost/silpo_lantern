"""G7 (§0, decision D-G7-01): a gate test guarding against the exact leak the
G7 stage plan's own adversarial audit found in its first revision -- a
committed `Receipt.before_state`/`after_state` (full `Cart.model_dump()`
dumps, `domain/models.py`) or a raw MCP capture carries `latitude`/
`longitude`/`address`, the guest's real delivery location. `make secret-scan`
does not catch this: `scripts/secret_scan.py` matches only API-key/bearer/
secret SHAPES, not PII fields with ordinary numeric or string values.

Scoped to every tracked file under `datasets/` (`raw/` is untracked --
`.gitignore` -- so it is not walked here; that directory's whole reason to
exist is that its contents are exactly this kind of unsanitized capture).
Permanent, not scoped to the G7 stage: nothing else in the gate stops a
future sanitized/replay fixture from acquiring the same problem.
"""

import json
from pathlib import Path
from typing import Any

from src.lantern.config import PROJECT_ROOT

DATASETS_ROOT = PROJECT_ROOT / "datasets"
FORBIDDEN_KEYS = {"latitude", "longitude", "address"}


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    """Walks a decoded JSON document for any dict key in FORBIDDEN_KEYS, at
    any nesting depth -- a coordinate pair can arrive nested inside a cart,
    a shipment, or a channel snapshot, and a shallow check would miss it."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if key in FORBIDDEN_KEYS:
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
