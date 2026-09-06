"""`Gap` must never be a Pydantic field type anywhere in `domain/`
— it has no `__get_pydantic_core_schema__` and loses its own subclass
identity under ordinary arithmetic (measured directly).
An AST scan, not a single example, because a future addition could
reintroduce the mistake in a module this test doesn't otherwise import.
"""

import ast
from pathlib import Path

DOMAIN_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "lantern" / "domain"
)


def _annotations_mentioning_gap(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and stmt.annotation is not None:
                    annotation_src = ast.dump(stmt.annotation)
                    if "'Gap'" in annotation_src or "id='Gap'" in annotation_src:
                        hits.append(f"{path.name}:{node.name}.{ast.dump(stmt.target)}")
    return hits


def test_no_domain_model_field_is_typed_as_gap() -> None:
    violations: list[str] = []
    for path in DOMAIN_DIR.glob("*.py"):
        if path.name == "diagnosis.py":
            # Gap is legitimately DEFINED here as a return type; the check
            # is about it being used as a *field* elsewhere.
            continue
        violations.extend(_annotations_mentioning_gap(path))
    assert not violations, f"Gap used as a model field: {violations}"


def test_gap_loses_subclass_identity_under_arithmetic_documented_behavior() -> None:
    """Pin the exact measured behavior this design works around, so a
    future dependency bump that changes it is caught here first."""
    from decimal import Decimal

    from src.lantern.domain.diagnosis import Gap

    g = Gap(Decimal("39.27"), is_borderline=False)
    assert type(g) is Gap
    result = g + Decimal("1")
    assert type(result) is Decimal  # not Gap — this is exactly why it's never stored
    assert not hasattr(result, "is_borderline")
