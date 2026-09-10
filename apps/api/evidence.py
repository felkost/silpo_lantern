"""G10 (D-G10-08): the console's evidence, read from two TRACKED files and
projected down to what a jury may see. The observation file carries the
author's own notes and screenshot provenance; only the app's rendered
lines, the codes, their levels and whether the app rendered them reach
the wire -- never a screenshot, a name, an address or a cart id.
"""

import json
from typing import Any, Dict, List

from src.lantern.config import PROJECT_ROOT

GOLDEN = PROJECT_ROOT / "datasets" / "golden-v1.0.0"
METRICS_PATH = GOLDEN / "metrics.json"
OBSERVATIONS_PATH = GOLDEN / "disclosure_audit" / "observations.json"


def _disclosure(document: Dict[str, Any]) -> Dict[str, Any]:
    counted: List[Dict[str, Any]] = [
        row
        for row in document.get("observations", [])
        if row.get("visibility_verified")
    ]
    row = counted[0] if counted else {}
    return {
        "state": row.get("state", ""),
        "observed_at": row.get("observed_at", ""),
        "products_total": row.get("cart_products_total"),
        "app_showed": list(row.get("app_showed", [])),
        "validations": [
            {
                "code": v["code"],
                "level": v["level"],
                "rendered_by_app": bool(v.get("rendered_by_app")),
            }
            for v in row.get("cart_validations", [])
        ],
    }


def load_evidence() -> Dict[str, Any]:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    observations = json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))
    return {
        "population": metrics["population"],
        "generated_at": metrics["generated_at"],
        "regenerate": metrics["regenerate"],
        "metrics": metrics["metrics"],
        "disclosure": _disclosure(observations),
    }
