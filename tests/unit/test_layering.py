"""Enforce this project's Clean Architecture layer table by walking
imports, not by trusting directory placement alone. Adapted from the donor
project's `SupportFlow/tests/test_layering.py` — the shape (LAYER_OF +
ALLOWED map, AST-walk, one negative rule beyond the plain cross-layer
check) is reused directly; only the layer names and the write-allowlist
rule are Lantern's own.

The layer table this test enforces: kernel (settings, no project-local
imports) -> domain (business rules, imports kernel only) -> safety (Write
Guard, imports kernel+domain) -> infra (MCP/DB/tracing, imports
kernel+domain) -> application (the agent graph, imports all of the above).
"""

import ast
import re
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

# Project invariant: "the domain core does no I/O" — domain and safety must
# never import a networking, LLM, or database library, because otherwise one
# convenient edit turns a pure, offline-testable rule into something that
# silently needs a live connection to pass its own unit test.
#
# `langchain_openai`/`langchain_core` added in
# the same commit as the `langchain-openai` pin in requirements.txt —
# neither the pre-existing "langchain" nor "openai" entries match this
# package's actual top-level module name.
FORBIDDEN_FOR_DOMAIN_AND_SAFETY = {
    "httpx",
    "requests",
    "mcp",
    "langchain",
    "langchain_openai",
    "langchain_core",
    "langgraph",
    "openai",
    "fastapi",
    "sqlalchemy",
    "psycopg",
}


# DR-09: a parameter in this shape
# is exactly what would let an LLM-facing function receive (and therefore
# implicitly be trusted to have computed) a gap or a total directly, instead
# of deriving it from a `Diagnosis` the domain layer already produced. Matched
# on the parameter's own name/annotation, not on where the value came from —
# the point is that such a parameter should not exist in these two layers at
# all, not that its provenance needs to be double-checked.
_GAP_OR_TOTAL_PARAM_NAME = re.compile(r".*_(gap|total)$", re.IGNORECASE)
_GAP_OR_TOTAL_ANNOTATIONS = {"Gap"}


def _annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dr09_violations_in_tree(tree: ast.AST, rel_path: str) -> list[str]:
    """Pure AST-level detector, kept separate from file/layer discovery so it
    can be exercised directly against a synthetic violation (see
    `test_dr09_ast_rule_detects_synthetic_violation` below) without needing a
    real file under `src/lantern/`.
    """
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        all_params = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        for arg in all_params:
            annotation = _annotation_name(arg.annotation)
            name_matches = bool(_GAP_OR_TOTAL_PARAM_NAME.match(arg.arg))
            annotation_matches = annotation in _GAP_OR_TOTAL_ANNOTATIONS
            if name_matches or annotation_matches:
                violations.append(
                    f"{rel_path}:{node.name}: parameter '{arg.arg}' "
                    f"(annotation={annotation!r}) looks like a raw gap/total "
                    f"passed directly, instead of read from a Diagnosis"
                )
    return violations


def test_dr09_no_raw_gap_or_total_params_in_application_or_interface():
    """DR-09's enforcement half: no `application`/`interface` function may
    take a parameter named `*_gap`/`*_total` or annotated `Gap`. An earlier
    function-signature test only checked the contract at the call site;
    this is the AST rule that makes a *new* violation impossible to
    introduce unnoticed as the `application` layer gains real functions.
    """
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(SRC.parent)
        module_parts = rel.with_suffix("").parts
        this_layer = _layer_of_module(".".join(module_parts))
        if this_layer not in {"application", "interface"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_dr09_violations_in_tree(tree, str(rel)))
    assert not violations, "\n".join(violations)


def test_dr09_ast_rule_detects_synthetic_violation():
    """Proves the detector itself works, independent of whether any real
    file currently violates it (right now the
    `application` layer is still empty). Mirrors the project's own practice
    of demonstrating a new gate failing on a synthetic case before trusting
    it to pass on real code.
    """
    source = (
        "def explain(diagnosis, service_gap):\n"
        "    return diagnosis\n"
        "\n"
        "def plan(cart_total: 'Gap'):\n"
        "    return cart_total\n"
    )
    tree = ast.parse(source)
    violations = _dr09_violations_in_tree(tree, "synthetic.py")
    assert len(violations) == 2
    assert any("service_gap" in v for v in violations)
    assert any("cart_total" in v for v in violations)


def test_dr09_ast_rule_allows_diagnosis_typed_parameter():
    """The legitimate source of a gap/total is a `Diagnosis` object itself —
    a function taking `diagnosis: Diagnosis` and reading `.gap` internally
    must not be flagged."""
    source = (
        "def explain(diagnosis: Diagnosis) -> str:\n    return str(diagnosis.gap)\n"
    )
    tree = ast.parse(source)
    assert _dr09_violations_in_tree(tree, "synthetic.py") == []


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
    one's imports must stay within the layer table defined by LAYER_OF and
    ALLOWED above.
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
    """The single most load-bearing invariant in this project: a domain
    rule or the Write Guard that quietly starts importing `httpx`
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
    """Project invariant: only one node in the graph may call a write
    tool — enforced here by making the write-allowlist constant itself
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
