"""T22: the judges' declared boundary, enforced instead of
asserted.

The claim is that a judge never scores arithmetic, authorization, or
whether a write happened. Left as prose, that claim is unfalsifiable —
and a judge that quietly began rewarding correct arithmetic would be a
second, weaker opinion competing with a proof, since money and
post-conditions are decided by pure code and confirmed by an independent
read-back.

**How the pairs are built.** Take a real explainer sentence and change
ONLY the amount it names. Nothing else moves: same product, same
structure, same register. From the text alone the judge cannot tell which
figure is right — so if its score moves, it is reacting to the number
rather than to the writing, which is exactly the boundary being crossed.

**What "indistinguishable" is measured against.** Not a threshold someone
picked. GEval is stochastic: scoring the same text twice does not return
the same number, and comparing an effect against a made-up tolerance
would say more about the tolerance than about the judge. So each text is
scored TWICE, and the spread between repeats of the SAME text is the
judge's own noise floor. The boundary holds when swapping the amount
moves the score no more than re-asking about an unchanged text does.

Runs under `make eval` only — live LLM calls, real cost.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Tuple

import pytest

from src.lantern.config import PROJECT_ROOT, load_env

CALIBRATION_DIR = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "judge_calibration"
PAIRS_PATH = CALIBRATION_DIR / "pairs.json"
RESULT_PATH = PROJECT_ROOT / "datasets" / "evidence" / "judge_boundary_result.json"

# The amounts substituted in. Both are plausible sums for this cart, and
# neither is derivable as "the right one" from the sentence alone.
_ORIGINAL_MARKER = "₴"
_SUBSTITUTE = "63,40"


def _sentences_with_an_amount(limit: int) -> List[str]:
    """Real explainer sentences that name a sum. Taken from the tracked
    calibration set rather than written here, for the same reason the
    calibration pairs are: text authored by whoever writes the test is
    text chosen for how it will score."""
    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    found: List[str] = []
    for pair in pairs:
        if pair["kind"] != "constructed":
            continue
        text = pair["a"]["text"]
        if pair["a"]["origin"] != "live-explainer":
            text = pair["b"]["text"]
        if _ORIGINAL_MARKER in text and text not in found:
            found.append(text)
    return found[:limit]


def _swap_the_amount(text: str) -> str:
    """Replaces the numeral before the currency sign, leaving every other
    word untouched."""
    head, _, tail = text.partition(_ORIGINAL_MARKER)
    words = head.rstrip().split(" ")
    words[-1] = _SUBSTITUTE
    return " ".join(words) + " " + _ORIGINAL_MARKER + tail


def _judge_model() -> Tuple[Any, str]:
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("no OPENROUTER_API_KEY -- this is a live, paid job")

    import yaml
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    from src.lantern.evals.openrouter_judge import OpenRouterJudge
    from src.lantern.graph.llm_adapter import OPENROUTER_BASE_URL

    models = yaml.safe_load(
        (PROJECT_ROOT / "config" / "models.yaml").read_text(encoding="utf-8")
    )
    selected = models["eval_judge"]["selected"]
    client = ChatOpenAI(
        model=selected,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
    )
    return OpenRouterJudge(model=selected, client=client), selected


def _run_boundary() -> Dict[str, Any]:
    from src.lantern.evals.judges import JUDGE_STEPS, build_judge, score_text

    sentences = _sentences_with_an_amount(4)
    model, model_id = _judge_model()

    rows: List[Dict[str, Any]] = []
    for name in sorted(JUDGE_STEPS):
        metric = build_judge(name, model)
        for text in sentences:
            altered = _swap_the_amount(text)
            original_first = score_text(metric, text)
            original_again = score_text(metric, text)
            altered_score = score_text(metric, altered)
            rows.append(
                {
                    "judge": name,
                    "noise": abs(original_first - original_again),
                    "effect": abs(
                        mean([original_first, original_again]) - altered_score
                    ),
                    "scores": {
                        "original_first": original_first,
                        "original_again": original_again,
                        "altered": altered_score,
                    },
                }
            )

    per_judge = {}
    for name in sorted(JUDGE_STEPS):
        subset = [r for r in rows if r["judge"] == name]
        per_judge[name] = {
            "mean_noise": mean(r["noise"] for r in subset),
            "mean_effect": mean(r["effect"] for r in subset),
            "n": len(subset),
        }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": model_id,
        "what_varies": "the amount named in the sentence, and nothing else",
        "per_judge": per_judge,
        "rows": rows,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


@pytest.fixture(scope="module")
def boundary() -> Dict[str, Any]:
    return _run_boundary()


def test_the_altered_sentence_differs_only_in_the_amount() -> None:
    """Guards the experiment itself: if the substitution changed anything
    else, a moved score would prove nothing about the boundary."""
    for text in _sentences_with_an_amount(4):
        altered = _swap_the_amount(text)
        assert altered != text
        assert len(altered.split(" ")) == len(text.split(" "))
        assert altered.replace(_SUBSTITUTE, "") == text.replace(
            text.partition(_ORIGINAL_MARKER)[0].rstrip().split(" ")[-1], ""
        )


@pytest.mark.parametrize(
    "name",
    [
        "RecoveryExplanationQuality",
        "UserControlAndConsentClarity",
        "UncertaintyAndRefusal",
    ],
)
def test_changing_the_amount_moves_the_score_no_more_than_asking_twice(
    boundary: Dict[str, Any], name: str
) -> None:
    """The boundary, as a measurement. `mean_effect` is how much swapping
    the sum moved the score; `mean_noise` is how much the same judge moves
    on an unchanged text. An effect inside the noise is a judge that did
    not see the number."""
    stats = boundary["per_judge"][name]
    # The noise floor is measured on 2 repeats of 4 texts -- small, so
    # allow it a margin rather than demanding effect <= noise exactly.
    allowance = max(stats["mean_noise"] * 2, 0.05)
    assert stats["mean_effect"] <= allowance, (
        f"{name} reacted to the amount: effect {stats['mean_effect']:.3f} "
        f"against a noise floor of {stats['mean_noise']:.3f}. The judge is "
        "scoring arithmetic, which is decided by code and proved by the "
        "read-back, not by a model."
    )
