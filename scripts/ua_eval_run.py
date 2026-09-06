"""UA-Eval full run: for every explainer candidate in `config/models.yaml`,
calls the candidate model with every prompt in
`datasets/ua-eval-v1.0.0/prompts.json`, then scores each response with the
`eval_judge` model against the fixed rubric in `prompts/eval_judge_v1.md`.

Call volume: 4 candidates x 28 prompts = 112 generation calls, then 112
judge calls — matching prompts/eval_judge_v1.md's own "up to 120 calls"
estimate for the judge step, and the largest call volume in this stage.

Judge model: `x-ai/grok-4.6` — `eval_judge.selected` is still null in
`config/models.yaml` (a cost/availability decision), so this run picks the
cheaper of the two candidates to produce the recommendation; it does NOT
write `eval_judge.selected` itself (same non-auto-write discipline as
`scripts/iv05_catalogue_check.py` — a human decides).

Selection rule applied for the printed recommendation only: the CHEAPEST
candidate whose average rubric score (mean of grammar/naturalness/
term_accuracy across all responses) is >= 4 and whose critical-error count
is 0. This script never writes `explainer.selected` itself; the author
reviews the manual-review sample (10 responses per candidate, printed
separately) before deciding.

Requires a real OPENROUTER_API_KEY in `.env`. Never run by the offline gate
or any automated test — this is IV-05/UA-Eval territory, run by the author
on explicit go-ahead. Writes full raw results to
`datasets/evidence/ua_eval_<timestamp>.json` (gitignored).
"""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from src.lantern.config import PROJECT_ROOT, load_env  # noqa: E402
from src.lantern.graph.llm_adapter import (  # noqa: E402
    build_candidate_llm,
    build_eval_judge_llm,
    load_prompt_content,
    render_eval_judge_prompt,
)

MODELS_YAML_PATH = PROJECT_ROOT / "config" / "models.yaml"
PROMPTS_PATH = PROJECT_ROOT / "datasets" / "ua-eval-v1.0.0" / "prompts.json"
OUT_DIR = PROJECT_ROOT / "datasets" / "evidence"
JUDGE_MODEL = "x-ai/grok-4.6"  # cheaper of the two eval_judge candidates
MANUAL_REVIEW_SAMPLE_SIZE = 10


def _call_candidate(
    model_id: str,
    api_key: str,
    system_text: str,
    prompt: str,
    run_tags: List[str],
) -> Dict[str, Any]:
    llm = build_candidate_llm(model_id, api_key)
    started = time.monotonic()
    response = llm.invoke(
        [SystemMessage(content=system_text), HumanMessage(content=prompt)],
        config={"tags": run_tags + [model_id, "role:candidate"]},
    )
    elapsed = time.monotonic() - started
    usage = getattr(response, "usage_metadata", None) or {}
    return {
        "text": response.content,
        "elapsed_seconds": round(elapsed, 2),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def _call_judge(
    api_key: str,
    ua_eval_prompt: str,
    candidate_response: str,
    run_tags: List[str],
    candidate_model_id: str,
) -> Dict[str, Any]:
    llm = build_eval_judge_llm(JUDGE_MODEL, api_key)
    prompt = render_eval_judge_prompt(ua_eval_prompt, candidate_response)
    started = time.monotonic()
    score = llm.invoke(
        [HumanMessage(content=prompt)],
        config={
            "tags": run_tags
            + [JUDGE_MODEL, "role:judge", f"scoring:{candidate_model_id}"]
        },
    )
    elapsed = time.monotonic() - started
    return {"score": score.model_dump(), "elapsed_seconds": round(elapsed, 2)}


def main() -> int:
    # Windows' console defaults to a legacy codepage (cp1251) that cannot
    # encode most Ukrainian text — reconfigure stdout/stderr to UTF-8 so a
    # Cyrillic response doesn't crash the run's own summary/review printing
    # (measured: the 2026-09-06 run wrote all data successfully but then
    # crashed on UnicodeEncodeError while printing the manual-review sample).
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    load_env()
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set in .env — aborting.", file=sys.stderr)
        return 1

    models_config = yaml.safe_load(MODELS_YAML_PATH.read_text(encoding="utf-8"))
    candidates = models_config["explainer"]["candidates"]
    prompts = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    system_text = load_prompt_content("recovery_system")

    run_tags = ["ua-eval", f"run:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"]
    results: List[Dict[str, Any]] = []

    for candidate in candidates:
        model_id = candidate["model"]
        print(f"\n=== Candidate: {model_id} ===")
        for item in prompts:
            print(f"  {item['id']} ...", end=" ")
            try:
                generation = _call_candidate(
                    model_id, api_key, system_text, item["prompt_uk"], run_tags
                )
            except Exception as exc:  # noqa: BLE001 — record, don't crash the run
                print(f"GENERATION FAILED: {exc}")
                results.append(
                    {
                        "model_id": model_id,
                        "prompt_id": item["id"],
                        "error": f"generation: {exc}",
                    }
                )
                continue

            try:
                judged = _call_judge(
                    api_key, item["prompt_uk"], generation["text"], run_tags, model_id
                )
            except Exception as exc:  # noqa: BLE001
                print(f"JUDGE FAILED: {exc}")
                results.append(
                    {
                        "model_id": model_id,
                        "prompt_id": item["id"],
                        "generation": generation,
                        "error": f"judge: {exc}",
                    }
                )
                continue

            print(f"scored {judged['score']}")
            results.append(
                {
                    "model_id": model_id,
                    "prompt_id": item["id"],
                    "category": item["category"],
                    "generation": generation,
                    "judge": judged,
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"ua_eval_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")

    _print_summary(results, candidates)
    _print_manual_review_sample(results, candidates)
    return 0


def _print_summary(
    results: List[Dict[str, Any]], candidates: List[Dict[str, Any]]
) -> None:
    print(
        "\n=== Summary (recommendation only — author decides `explainer.selected`) ==="
    )
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for row in results:
        by_model.setdefault(row["model_id"], []).append(row)

    ranked = sorted(candidates, key=lambda c: c["price_usd_per_million"]["input"])
    for candidate in ranked:
        model_id = candidate["model"]
        rows = [r for r in by_model.get(model_id, []) if "judge" in r]
        if not rows:
            print(f"{model_id}: no scored responses (all failed)")
            continue
        scores = [r["judge"]["score"] for r in rows]
        avg = sum(
            (s["grammar"] + s["naturalness"] + s["term_accuracy"]) / 3 for s in scores
        ) / len(scores)
        critical_errors = sum(1 for s in scores if s["critical_error"])
        clears = avg >= 4 and critical_errors == 0
        print(
            f"{model_id}: avg={avg:.2f} critical_errors={critical_errors} "
            f"scored={len(rows)}/{len(results) // len(candidates)} "
            f"{'CLEARS threshold' if clears else 'does not clear'}"
        )


def _print_manual_review_sample(
    results: List[Dict[str, Any]], candidates: List[Dict[str, Any]]
) -> None:
    print(
        f"\n=== Manual review sample ({MANUAL_REVIEW_SAMPLE_SIZE} per candidate, "
        "author reviews before deciding) ==="
    )
    for candidate in candidates:
        model_id = candidate["model"]
        rows = [r for r in results if r["model_id"] == model_id and "generation" in r]
        sample = random.sample(rows, min(MANUAL_REVIEW_SAMPLE_SIZE, len(rows)))
        print(f"\n--- {model_id} ---")
        for row in sample:
            print(f"[{row['prompt_id']}] {row['generation']['text']}")


if __name__ == "__main__":
    sys.exit(main())
