"""D-G1-06 (reframed in round 2): a forward
constraint for G5+G6, not something this stage's own code can violate yet —
`src/lantern/safety/write_guard.py` doesn't exist. Honestly a tripwire, not
present-day coverage (round 2 correction): zero files anywhere in this repo
match `*allowlist*` today, so this test currently exercises nothing. Kept
anyway so the constraint is checked automatically the moment such a file is
added, rather than relying on someone remembering to write this check later.

Overlaps by design with `tests/unit/test_layering.py`'s
`test_write_allowlist_constant_only_imported_within_safety`, which guards a
different property (no direct import of the allowlist constant itself,
versus this test's "no `ToolAnnotations` import into an allowlist-named
module") — both currently no-op for the same reason.
"""

import ast
from pathlib import Path

from src.lantern.config import PROJECT_ROOT

SRC = PROJECT_ROOT / "src"


def _allowlist_named_files() -> list[Path]:
    if not SRC.exists():
        return []
    return [p for p in SRC.rglob("*.py") if "allowlist" in p.stem.lower()]


def test_no_allowlist_named_module_imports_tool_annotations() -> None:
    violations = []
    for path in _allowlist_named_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "mcp" in node.module
            ):
                for alias in node.names:
                    if alias.name == "ToolAnnotations":
                        violations.append(f"{path}: imports ToolAnnotations")
    assert not violations, "\n".join(violations)


def test_this_check_currently_has_nothing_to_exercise() -> None:
    """Documents the round-2 finding explicitly: this is a tripwire, not
    coverage, until G5+G6 creates a `*allowlist*`-named module.
    """
    assert _allowlist_named_files() == []
