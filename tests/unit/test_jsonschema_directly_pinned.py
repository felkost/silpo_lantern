"""`jsonschema` is already installed
transitively via `mcp`, but this project's fixture-validation pipeline
depends on it directly — pin it explicitly so a future
`mcp` bump can't silently drop it out from under an unrelated part of the
codebase.
"""

from src.lantern.config import PROJECT_ROOT


def test_requirements_txt_pins_jsonschema_directly() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert any(
        line.strip().startswith("jsonschema==") for line in requirements.splitlines()
    ), "jsonschema must be pinned directly in requirements.txt, not left transitive"
