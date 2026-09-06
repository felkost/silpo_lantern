"""IV-05: re-verifies every model id in `config/models.yaml` against
OpenRouter's live, public `/api/v1/models` catalogue — a free,
unauthenticated read (no LLM inference, no token cost), deliberately
separate from the smoke call. A model can still answer a smoke call while
having quietly changed price or been deprecated-but-still-served; this is
the check that would catch that.

Never writes to `config/models.yaml` itself — prints a report and exits
non-zero if any id is missing, priced differently than recorded, or has
less context window than the file's own `context_window_min_tokens`
declares as needed. A human decides what to do with a mismatch: silently
overwriting the file would hide exactly the drift this check exists to
surface.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import yaml  # noqa: E402

from src.lantern.config import PROJECT_ROOT  # noqa: E402

MODELS_YAML_PATH = PROJECT_ROOT / "config" / "models.yaml"
CATALOGUE_URL = "https://openrouter.ai/api/v1/models"
OUT_DIR = PROJECT_ROOT / "datasets" / "evidence"


def fetch_catalogue() -> Dict[str, Dict[str, Any]]:
    response = httpx.get(CATALOGUE_URL, timeout=15)
    response.raise_for_status()
    data = response.json()["data"]
    return {entry["id"]: entry for entry in data}


def _price_per_million(per_token_str: str) -> Decimal:
    return Decimal(per_token_str) * Decimal(1_000_000)


def check_one_model(
    model_id: str,
    recorded_price: Optional[Dict[str, float]],
    min_context_tokens: Optional[int],
    catalogue: Dict[str, Dict[str, Any]],
) -> List[str]:
    problems: List[str] = []
    entry = catalogue.get(model_id)
    if entry is None:
        problems.append(f"{model_id}: NOT FOUND in live catalogue")
        return problems

    live_input = _price_per_million(entry["pricing"]["prompt"])
    live_output = _price_per_million(entry["pricing"]["completion"])
    if recorded_price is not None:
        recorded_input = Decimal(str(recorded_price["input"]))
        recorded_output = Decimal(str(recorded_price["output"]))
        if live_input != recorded_input or live_output != recorded_output:
            problems.append(
                f"{model_id}: price drift — recorded "
                f"in={recorded_input}/out={recorded_output} per 1M, "
                f"live in={live_input}/out={live_output} per 1M"
            )

    if min_context_tokens is not None:
        live_context = entry.get("context_length") or 0
        if live_context < min_context_tokens:
            problems.append(
                f"{model_id}: context_length {live_context} < required "
                f"{min_context_tokens}"
            )

    return problems


def main() -> int:
    config = yaml.safe_load(MODELS_YAML_PATH.read_text(encoding="utf-8"))
    catalogue = fetch_catalogue()

    all_problems: List[str] = []
    checked_ids: List[str] = []

    planner = config["planner"]
    checked_ids += [planner["model"], planner["fallback"]]
    all_problems += check_one_model(
        planner["model"],
        planner.get("price_usd_per_million"),
        planner.get("context_window_min_tokens"),
        catalogue,
    )
    all_problems += check_one_model(planner["fallback"], None, None, catalogue)

    explainer = config["explainer"]
    for candidate in explainer["candidates"]:
        checked_ids.append(candidate["model"])
        all_problems += check_one_model(
            candidate["model"],
            candidate.get("price_usd_per_million"),
            explainer.get("context_window_min_tokens"),
            catalogue,
        )

    for candidate in config["eval_judge"]["candidates"]:
        checked_ids.append(candidate["model"])
        all_problems += check_one_model(
            candidate["model"], candidate.get("price_usd_per_million"), None, catalogue
        )

    print(f"Checked against {len(catalogue)} live catalogue entries.\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        OUT_DIR
        / f"iv05_catalogue_check_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "catalogue_size": len(catalogue),
                "checked_models": {
                    model_id: catalogue.get(model_id) for model_id in checked_ids
                },
                "problems": all_problems,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}\n")

    if not all_problems:
        print("All model ids/prices/context windows match the live catalogue.")
        return 0

    print(f"{len(all_problems)} problem(s) found:\n")
    for problem in all_problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
