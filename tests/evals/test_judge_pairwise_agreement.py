"""T20b: ask the judge the question the human was actually asked.

The first calibration compared two things that were never the same
question. The author was shown both texts and asked which is better; the
judge was shown one text at a time and asked for an absolute score, and a
preference was then inferred by comparing two numbers. That inference is
weak where it matters: the median gap between the two scores was 0.10 --
one step of the scale the judge actually uses -- so half the "preferences"
were a single quantisation step.

Here the judge sees both texts at once and answers A, B or tie, exactly as
the author did.

**Position bias is measured, not hoped away.** An LLM asked to choose
between two options tends to favour one position. So every pair is asked
TWICE, with the members swapped, and a preference counts only when both
orders agree; when they disagree the judge is recorded as unstable on
that pair and it leaves the denominator. The rate of such flips is
reported -- it is a property of the judge worth knowing on its own, and it
cannot be recovered from a single-order run.

Runs under `make eval` only -- live LLM calls.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from src.lantern.config import PROJECT_ROOT, load_env
from src.lantern.evals.judges import JUDGE_STEPS

CALIBRATION_DIR = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "judge_calibration"
PAIRS_PATH = CALIBRATION_DIR / "pairs.json"
LABELS_PATH = CALIBRATION_DIR / "labels.json"
EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"

_PROMPT = """You are comparing two messages a shopping assistant could send
to a Ukrainian-speaking customer. Apply exactly these criteria, in order:

{steps}

Message 1:
{first}

Message 2:
{second}

Which message is better by those criteria? Answer with exactly one token:
"1" if the first is better, "2" if the second is better, or "tie" if they
are genuinely equivalent. No explanation."""


def _result_path(model_id: str) -> Path:
    slug = model_id.replace("/", "_").replace(":", "_")
    return EVIDENCE_DIR / f"judge_pairwise_result_{slug}.json"


def _client() -> Tuple[Any, str]:
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("no OPENROUTER_API_KEY -- this is a live, paid job")

    import yaml
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    from src.lantern.graph.llm_adapter import OPENROUTER_BASE_URL

    models = yaml.safe_load(
        (PROJECT_ROOT / "config" / "models.yaml").read_text(encoding="utf-8")
    )
    selected = (
        os.environ.get("LANTERN_EVAL_JUDGE_MODEL") or models["eval_judge"]["selected"]
    )
    client = ChatOpenAI(
        model=selected,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        temperature=0,
    )
    return client, selected


def _ask(client: Any, dimension: str, first: str, second: str) -> str:
    """Returns '1', '2' or 'tie' -- about the ORDER SHOWN, not about the
    pair's own A/B, which the caller maps back."""
    prompt = _PROMPT.format(
        steps="\n".join(f"- {step}" for step in JUDGE_STEPS[dimension]),
        first=first,
        second=second,
    )
    answer = str(client.invoke(prompt).content).strip().lower()
    if answer.startswith("1"):
        return "1"
    if answer.startswith("2"):
        return "2"
    return "tie"


def _run() -> Dict[str, Any]:
    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    label_doc = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    labels = label_doc["labels"]
    excluded = {entry["pair_id"] for entry in label_doc.get("excluded", [])}
    client, model_id = _client()

    rows: List[Dict[str, Any]] = []
    for pair in pairs:
        pid = pair["pair_id"]
        if pid in excluded or pid not in labels:
            continue
        a, b = pair["a"]["text"], pair["b"]["text"]

        forward = _ask(client, pair["dimension"], a, b)
        reverse = _ask(client, pair["dimension"], b, a)
        # Map each answer back to the pair's own A/B.
        forward_pick = {"1": "A", "2": "B", "tie": "tie"}[forward]
        reverse_pick = {"1": "B", "2": "A", "tie": "tie"}[reverse]

        stable = forward_pick == reverse_pick
        judge = forward_pick if stable else "unstable"
        human = labels[pid]
        rows.append(
            {
                "pair_id": pid,
                "kind": pair["kind"],
                "dimension": pair["dimension"],
                "forward": forward_pick,
                "reverse": reverse_pick,
                "stable": stable,
                "judge": judge,
                "human": human,
                "comparable": stable and judge != "tie" and human != "tie",
                "agree": stable and judge == human,
            }
        )

    def summarise(kind: str) -> Dict[str, Any]:
        subset = [r for r in rows if r["kind"] == kind]
        comparable = [r for r in subset if r["comparable"]]
        agreed = sum(1 for r in comparable if r["agree"])
        return {
            "pairs": len(subset),
            "order_flips": sum(1 for r in subset if not r["stable"]),
            "comparable": len(comparable),
            "agreed": agreed,
            "agreement": (agreed / len(comparable)) if comparable else None,
        }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": model_id,
        "method": "pairwise, both orders, preference counted only when the "
        "two orders agree",
        "constructed": summarise("constructed"),
        "natural": summarise("natural"),
        "rows": rows,
    }
    out = _result_path(model_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["result_path"] = str(out)
    return result


@pytest.fixture(scope="module")
def pairwise() -> Dict[str, Any]:
    return _run()


def test_the_judge_still_passes_the_pairs_whose_answer_is_not_taste(
    pairwise: Dict[str, Any],
) -> None:
    """The same broken-judge detector as the scoring run. If asking
    pairwise broke THIS, the new method is worse and its other numbers
    mean nothing."""
    constructed = pairwise["constructed"]
    assert constructed["comparable"] > 0
    assert (
        constructed["agreement"] == 1.0
    ), f"pairwise asking lost the structural pairs: {constructed}"


def test_the_judge_is_stable_under_swapping_the_two_texts(
    pairwise: Dict[str, Any],
) -> None:
    """A judge that answers differently when the same two texts change
    places is reporting position, not preference. Reported as a rate
    rather than assumed to be zero; the bar is deliberately loose because
    what matters is whether a stable signal exists at all."""
    total = pairwise["constructed"]["pairs"] + pairwise["natural"]["pairs"]
    flips = pairwise["constructed"]["order_flips"] + pairwise["natural"]["order_flips"]
    assert flips / total <= 0.5, (
        f"the judge flipped its answer on {flips} of {total} pairs when the "
        "texts swapped places -- it is answering about order, not quality"
    )


def test_the_pairwise_agreement_is_reported(pairwise: Dict[str, Any]) -> None:
    assert Path(pairwise["result_path"]).is_file()
    assert pairwise["natural"]["agreement"] is not None


def test_asking_the_same_question_as_the_human_beats_chance(
    pairwise: Dict[str, Any],
) -> None:
    """The point of this module -- and the bar is the interval's LOWER
    BOUND, not the point estimate.

    The first version asserted `agreement > 0.5`, which the first live run
    passed at 6/10 = 0.60. But the 95% Wilson interval for 6 of 10 is
    [0.31, 0.83]: it covers chance completely, so passing that assertion
    would have turned `make eval` green on a number that establishes
    nothing. The same discipline the results chart applies to every
    metric applies here.

    Reaching this bar is a question of sample size as much as of judge
    quality, and the arithmetic is unforgiving at agreement this low:
    holding 0.60, the lower bound clears 0.5 only at 97 comparable pairs.
    At 0.70 it takes 25, at 0.75 sixteen. So the honest routes are a
    judge that agrees MORE often, or several times more labelling -- not
    a softer test.
    """
    from scripts.render_metrics_chart import wilson

    natural = pairwise["natural"]
    low, high = wilson(natural["agreement"], natural["comparable"])
    assert low > 0.5, (
        "the judge's agreement with the author does not exclude chance: "
        f"{natural['agreed']}/{natural['comparable']} = "
        f"{natural['agreement']:.3f}, 95% interval [{low:.3f}, {high:.3f}]"
    )
