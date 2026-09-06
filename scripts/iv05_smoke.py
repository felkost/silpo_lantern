"""IV-05 narrow smoke: one live call each to the planner model and its
fallback, on SYNTHETIC state (no live MCP read) — proves the OpenRouter API
key works, the pinned model ids are still valid, tool calling / structured
output binds correctly for this model+provider pair, and records real token
usage against `config/models.yaml`'s own estimate. This is deliberately
narrower than a full graph run: no live MCP fetchers are wired yet (a
separate piece of work), so this exercises the LLM call layer only.

Never run by the offline gate or any automated test. Requires a real
OPENROUTER_API_KEY in `.env`. Prints a summary; writes the full raw
responses to `datasets/evidence/iv05_smoke_<timestamp>.json` (gitignored —
this is a local record, not a fixture) so the actual token counts and
model ids used are on disk, not just in a terminal that scrolls away.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from src.lantern.config import PROJECT_ROOT, load_env  # noqa: E402
from src.lantern.domain.disclosure import DisclosureReport  # noqa: E402
from src.lantern.domain.models import Diagnosis  # noqa: E402
from src.lantern.graph.llm_adapter import (  # noqa: E402
    OPENROUTER_BASE_URL,
    render_planner_prompt,
)
from src.lantern.graph.schemas import SearchIntent  # noqa: E402
from src.lantern.graph.state import RecoveryState, new_recovery_state  # noqa: E402

MODELS_YAML_PATH = PROJECT_ROOT / "config" / "models.yaml"
OUT_DIR = PROJECT_ROOT / "datasets" / "evidence"


def _synthetic_state() -> RecoveryState:
    """Gap 194.11, order.cost.min — a real, already-measured scenario, not
    an invented one — with no live MCP call behind it. Matches
    `tests/unit/test_llm_adapter_prompt_loading.py`'s own fixture shape."""
    state = new_recovery_state(
        session_id="iv05-smoke",
        trace_id="iv05-smoke",
        now=datetime.now(timezone.utc),
    )
    state["diagnosis"] = Diagnosis(
        blockers=[],
        disclosures=[],
        gap=Decimal("194.11"),
        gap_is_borderline=False,
        primary_code="order.cost.min",
        threshold_source="validation_context",
    )
    state["disclosure"] = DisclosureReport(
        blockers=[], disclosures=[], gap=Decimal("194.11"), gap_is_borderline=False
    )
    return state


def _call_one_model(
    model_id: str, api_key: str, system_text: str, human_text: str
) -> Dict[str, Any]:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model_id, base_url=OPENROUTER_BASE_URL, api_key=SecretStr(api_key)
    )
    structured = llm.with_structured_output(SearchIntent, include_raw=True)

    started = time.monotonic()
    result = structured.invoke(
        [SystemMessage(content=system_text), HumanMessage(content=human_text)]
    )
    elapsed = time.monotonic() - started

    raw = result["raw"]
    parsed = result["parsed"]
    parsing_error = result.get("parsing_error")

    usage = getattr(raw, "usage_metadata", None) or {}
    return {
        "model_id": model_id,
        "elapsed_seconds": round(elapsed, 2),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "parsed_search_intent": parsed.model_dump() if parsed is not None else None,
        "parsing_error": str(parsing_error) if parsing_error else None,
    }


def main() -> int:
    load_env()
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set in .env — aborting.", file=sys.stderr)
        return 1

    models_config = yaml.safe_load(MODELS_YAML_PATH.read_text(encoding="utf-8"))
    planner_model = models_config["planner"]["model"]
    fallback_model = models_config["planner"]["fallback"]

    state = _synthetic_state()
    system_text = (
        "You are the reasoning component of Lantern. Given the diagnosis "
        "below, propose 1-5 short search terms for products that could "
        "help clear the blocking gap. Output only the SearchIntent JSON."
    )
    human_text = render_planner_prompt(state, tool_view=[])

    results = []
    for label, model_id in [("planner", planner_model), ("fallback", fallback_model)]:
        print(f"Calling {label} ({model_id})...")
        try:
            outcome = _call_one_model(model_id, api_key, system_text, human_text)
            outcome["role"] = label
            results.append(outcome)
            tokens = outcome["total_tokens"]
            seconds = outcome["elapsed_seconds"]
            print(f"  OK — {tokens} tokens, {seconds}s")
            print(f"  SearchIntent: {outcome['parsed_search_intent']}")
        except (
            Exception
        ) as exc:  # noqa: BLE001 — smoke script: report, don't crash the run
            results.append({"role": label, "model_id": model_id, "error": str(exc)})
            print(f"  FAILED: {exc}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"iv05_smoke_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
