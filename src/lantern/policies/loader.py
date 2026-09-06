"""Loads `registry.yaml`, validated against `registry.schema.json`.
`PolicyRegistry.lookup` is exact-match only — no substring, prefix, or
case-folded comparison, ever: a lookup shortcut that matched
`product.offer.status.not_available` against the registered
`product.offer.not_found` would silently misclassify a quarantined code
as the confirmed one, exactly the alias the fail-safe exists to
prevent.
"""

from pathlib import Path
from typing import Optional

import jsonschema
import yaml

from src.lantern.domain.models import PolicyEntry

_REGISTRY_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = _REGISTRY_DIR / "registry.yaml"
DEFAULT_SCHEMA_PATH = _REGISTRY_DIR / "registry.schema.json"


class PolicyRegistrySchemaError(ValueError):
    """`registry.yaml` does not validate against `registry.schema.json` —
    raised loud rather than loading a malformed registry silently."""


class PolicyRegistry:
    """Exact-match `code -> PolicyEntry` lookup. A miss returns `None`,
    which `diagnosis.diagnose()` treats as the fail-safe: disclosed,
    never planned against, never aliased."""

    def __init__(self, entries: dict[str, PolicyEntry]) -> None:
        self._entries = entries

    def lookup(self, code: str) -> Optional[PolicyEntry]:
        return self._entries.get(code)

    def __len__(self) -> int:
        return len(self._entries)


def load_registry(
    yaml_path: Path = DEFAULT_REGISTRY_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> PolicyRegistry:
    import json

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=raw, schema=schema)
    except jsonschema.ValidationError as exc:
        raise PolicyRegistrySchemaError(str(exc)) from exc

    entries = {entry["code"]: PolicyEntry(**entry) for entry in raw["entries"]}
    return PolicyRegistry(entries)
