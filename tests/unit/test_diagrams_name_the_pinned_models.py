"""The deployment and LLM-sequence diagrams name the models by id, and
`config/models.yaml` is the only place a model is chosen -- so the two must
agree, or a model swap leaves the site showing the old one. Checked on the
rendered architecture page, where both diagrams are inlined, with the
id's short form (after the vendor slash), which is what fits a block.
"""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_the_architecture_page_diagrams_carry_the_pinned_model_ids() -> None:
    models = yaml.safe_load(
        (PROJECT_ROOT / "config" / "models.yaml").read_text(encoding="utf-8")
    )
    pinned = {
        "planner": models["planner"]["model"],
        "explainer": models["explainer"]["selected"],
        "eval judge": models["eval_judge"]["selected"],
    }
    page = (PROJECT_ROOT / "docs" / "reports" / "architecture.html").read_text(
        encoding="utf-8"
    )
    missing = {
        role: model
        for role, model in pinned.items()
        if f"{role} · {model.split('/', 1)[1]}" not in page
    }
    assert not missing, f"diagram labels lag config/models.yaml: {missing}"
