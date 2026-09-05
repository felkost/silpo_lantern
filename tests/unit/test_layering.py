"""Enforce the layer table in CLAUDE.md by walking imports, not by trusting
directory placement alone. Adapted from the donor project's
`SupportFlow/tests/test_layering.py` — the shape (LAYER_OF + ALLOWED map,
AST-walk, one negative rule beyond the plain cross-layer check) is reused
directly; only the layer names and the write-allowlist rule are Lantern's
own.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent / "src"

# Package name (inside src/lantern/) -> layer name. A layer may always
# import itself.
LAYER_OF = {
    "config": "kernel",
    "domain": "domain",
    "policies": "domain",
    "safety": "safety",
    "mcp": "infra",
    "memory": "infra",
    "observability": "infra",
    "graph": "application",
    "prompts": "application",
}

ALLOWED: dict[str, set[str]] = {
    "kernel": set(),
    "domain": {"kernel"},
    "safety": {"kernel", "domain"},
    "infra": {"kernel", "domain"},
    "application": {"kernel", "domain", "safety", "infra"},
}

# CLAUDE.md invariant: "The domain core does no I/O" — domain and safety must
# never import a networking, LLM, or database library, because otherwise one
# convenient edit turns a pure, offline-testable rule into something that
# silently needs a live connection to pass its own unit test.
FORBIDDEN_FOR_DOMAIN_AND_SAFETY = {
    "httpx",
    "requests",
    "mcp",
    "langchain",
    "langgraph",
    "openai",
    "fastapi",
    "sqlalchemy",
    "psycopg",
}


def _layer_of_module(module: str) -> str | None:
    """`module` is a dotted path like `src.lantern.domain.cart` or
    `src.lantern.config`. Returns the layer name, or None for anything
    outside `src.lantern` (stdlib, third-party, or apps/).
    """
    parts = module.split(".")
    if len(parts) < 3 or parts[0] != "src" or parts[1] != "lantern":
        return None
    return LAYER_OF.get(parts[2])


def _iter_python_files():
    if not SRC.exists():
        return
    yield from SRC.rglob("*.py")


def _imported_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module]
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def test_no_python_files_yet_or_all_respect_layering():
    """No lantern/ source files exist yet at kickoff; once they do, each
    one's imports must stay within what CLAUDE.md's layer table allows.
    """
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(SRC.parent)
        module_parts = rel.with_suffix("").parts
        module = ".".join(module_parts)
        this_layer = _layer_of_module(module)
        if this_layer is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for name in _imported_names(node):
                imported_layer = _layer_of_module(name)
                if imported_layer is None or imported_layer == this_layer:
                    continue
                if imported_layer not in ALLOWED[this_layer]:
                    violations.append(
                        f"{rel}: layer '{this_layer}' may not import "
                        f"layer '{imported_layer}' ({name})"
                    )
    assert not violations, "\n".join(violations)


def test_domain_and_safety_never_import_io_libraries():
    """The single most load-bearing rule in CLAUDE.md's invariants section:
    a domain rule or the Write Guard that quietly starts importing `httpx`
    or `mcp` stops being unit-testable offline, and every existing test can
    stay green while the guarantee it exists to protect is already gone.
    """
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(SRC.parent)
        module_parts = rel.with_suffix("").parts
        this_layer = _layer_of_module(".".join(module_parts))
        if this_layer not in {"domain", "safety"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for name in _imported_names(node):
                top_level = name.split(".")[0]
                if top_level in FORBIDDEN_FOR_DOMAIN_AND_SAFETY:
                    violations.append(f"{rel}: imports forbidden module '{name}'")
    assert not violations, "\n".join(violations)


def test_write_allowlist_constant_only_imported_within_safety():
    """CLAUDE.md invariant: 'only one node in the graph may call a write
    tool' — enforced here by making the write-allowlist constant itself
    unimportable from outside `lantern/safety/**`. Once
    `src/lantern/safety/write_guard.py` defines `WRITE_TOOL_ALLOWLIST`, any
    module outside `safety` importing it directly (instead of going through
    the Write Guard's own authorization function) fails this test.
    """
    allowlist_module = SRC / "lantern" / "safety" / "write_guard.py"
    if not allowlist_module.exists():
        return
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(SRC.parent)
        if "safety" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "write_guard" in node.module:
                    for alias in node.names:
                        if alias.name == "WRITE_TOOL_ALLOWLIST":
                            violations.append(
                                f"{rel}: imports WRITE_TOOL_ALLOWLIST directly"
                            )
    assert not violations, "\n".join(violations)
