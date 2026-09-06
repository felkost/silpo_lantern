"""Retries the UA-Eval prompts that failed with a provider-side error in a
previous full run (`scripts/ua_eval_run.py`) — e.g. qwen/qwen3.8-flash's
2026-09-06 run hit OpenRouter's shared-pool 429 rate limit on 10/28 prompts.
Reuses the same candidate/judge call functions and tags, so retried rows are
indistinguishable from a normal run except for a `retried: true` marker and
a short backoff between attempts (the failure was rate-limiting, not a bad
prompt, so an immediate retry without backoff would likely repeat it).

Never run by the offline gate or any automated test — same IV-05/UA-Eval
territory as `ua_eval_run.py`. Merges retried results into a COPY of the
input file (never overwrites the original run's own evidence record).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import load_env  # noqa: E402
from src.lantern.graph.llm_adapter import load_prompt_content  # noqa: E402
from scripts.ua_eval_run import (  # noqa: E402
    OUT_DIR,
    PROMPTS_PATH,
    _call_candidate,
    _call_judge,
)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 8


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if len(sys.argv) != 2:
        print(
            "usage: ua_eval_retry_failed.py <path to ua_eval_<ts>.json>",
            file=sys.stderr,
        )
        return 1

    load_env()
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set in .env — aborting.", file=sys.stderr)
        return 1

    in_path = Path(sys.argv[1])
    results: List[Dict[str, Any]] = json.loads(in_path.read_text(encoding="utf-8"))
    prompts_by_id = {
        p["id"]: p for p in json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    }
    system_text = load_prompt_content("recovery_system")
    run_tags = ["ua-eval", "retry", f"run:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"]

    failed_indices = [i for i, r in enumerate(results) if "error" in r]
    print(f"Found {len(failed_indices)} failed row(s) to retry.")

    for idx in failed_indices:
        row = results[idx]
        model_id = row["model_id"]
        item = prompts_by_id[row["prompt_id"]]
        print(f"  retrying {model_id} / {item['id']} ...", end=" ")

        generation = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                generation = _call_candidate(
                    model_id, api_key, system_text, item["prompt_uk"], run_tags
                )
                break
            except Exception as exc:  # noqa: BLE001
                print(f"attempt {attempt} failed ({exc}); ", end=" ")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_SECONDS)

        if generation is None:
            print("still failing, leaving as error.")
            continue

        try:
            judged = _call_judge(
                api_key, item["prompt_uk"], generation["text"], run_tags, model_id
            )
        except Exception as exc:  # noqa: BLE001
            print(f"judge failed: {exc}")
            results[idx] = {
                "model_id": model_id,
                "prompt_id": item["id"],
                "generation": generation,
                "error": f"judge: {exc}",
            }
            continue

        print(f"scored {judged['score']}")
        results[idx] = {
            "model_id": model_id,
            "prompt_id": item["id"],
            "category": item["category"],
            "generation": generation,
            "judge": judged,
            "retried": True,
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{in_path.stem}_retried.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")

    still_failed = [r["prompt_id"] for r in results if "error" in r]
    if still_failed:
        print(f"Still failing after retry: {still_failed}")
    else:
        print("All rows now scored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
