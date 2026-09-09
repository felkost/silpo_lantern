"""T20: the judge's agreement with a human, measured rather than assumed.

Runs under `make eval` only -- it makes live LLM calls and costs money.

**What is being measured.** For each pair, the judge scores both members
and its preference is whichever scores higher. The author labelled the
same pairs blind (`datasets/golden-v1.0.0/judge_calibration/labels.json`),
seeing neither the models behind the texts nor which member was
constructed. Agreement is how often the two picked the same member.

**Two populations, reported apart, because they mean different things.**

* CONSTRUCTED pairs (7) delete the amount clause from a real explainer
  sentence, so the better member follows from the construction and the
  author agreed with all seven. A judge that cannot pass these is broken,
  and this is the only part with a hard threshold.
* NATURAL pairs (16) are two different models answering the same UA-Eval
  prompt. Nobody knows the better one in advance -- which is what makes
  agreement here informative, and also why it carries NO threshold on the
  first run. Plan §14's rule is that a threshold starts from the measured
  baseline and may afterwards only be raised; inventing one now, after
  seeing the number, would be the opposite.

**Ties are not disagreements.** Where the author saw no difference, there
is nothing for the judge to agree or disagree with, and forcing that into
one bucket or the other would report an opinion as a measurement. Tie
pairs are excluded from the denominator and counted separately.

The result is written to `datasets/evidence/judge_calibration_result.json`
so the reported statistic has an artefact behind it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.lantern.config import PROJECT_ROOT, load_env

CALIBRATION_DIR = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "judge_calibration"
PAIRS_PATH = CALIBRATION_DIR / "pairs.json"
LABELS_PATH = CALIBRATION_DIR / "labels.json"
EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"


def _result_path(model_id: str) -> Path:
    """One artefact per judge model. A candidate is measured against the
    UNCHANGED set, so the results must sit side by side rather than
    overwrite each other -- otherwise "we tried another model" is a claim
    with nothing behind it."""
    slug = model_id.replace("/", "_").replace(":", "_")
    return EVIDENCE_DIR / f"judge_calibration_result_{slug}.json"


# A-priori, set before the run: the constructed pairs state what they are
# for. One member says what the change costs and the other does not, and
# the author agreed with the construction 7 times out of 7.
CONSTRUCTED_FLOOR = 1.0


def _judge_model() -> Any:
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
    # A candidate can be measured without editing `selected`: swapping
    # the configured judge on a hunch, before the measurement that would
    # justify it, is how an unjustified choice becomes the default.
    selected = (
        os.environ.get("LANTERN_EVAL_JUDGE_MODEL") or models["eval_judge"]["selected"]
    )
    assert selected, "config/models.yaml has no eval_judge.selected"
    client = ChatOpenAI(
        model=selected,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
    )
    return OpenRouterJudge(model=selected, client=client), selected


def _run_calibration() -> Dict[str, Any]:
    from src.lantern.evals.judges import build_judge, score_text

    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]
    model, model_id = _judge_model()

    metrics: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    for pair in pairs:
        human = labels.get(pair["pair_id"])
        if human is None:
            continue
        dimension = pair["dimension"]
        if dimension not in metrics:
            metrics[dimension] = build_judge(dimension, model)
        metric = metrics[dimension]

        a = score_text(metric, pair["a"]["text"])
        b = score_text(metric, pair["b"]["text"])
        if a == b:
            judge = "tie"
        else:
            judge = "A" if a > b else "B"

        rows.append(
            {
                "pair_id": pair["pair_id"],
                "kind": pair["kind"],
                "dimension": dimension,
                "score_a": a,
                "score_b": b,
                "judge": judge,
                "human": human,
                # A pair either side called a tie is not a disagreement:
                # there is nothing to agree about.
                "comparable": human != "tie" and judge != "tie",
                "agree": human == judge,
            }
        )

    def summarise(kind: str) -> Dict[str, Any]:
        subset = [r for r in rows if r["kind"] == kind]
        comparable = [r for r in subset if r["comparable"]]
        agreed = sum(1 for r in comparable if r["agree"])
        return {
            "pairs": len(subset),
            "comparable": len(comparable),
            "ties_excluded": len(subset) - len(comparable),
            "agreed": agreed,
            "agreement": (agreed / len(comparable)) if comparable else None,
        }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": model_id,
        "labeller": "author",
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
def calibration() -> Dict[str, Any]:
    return _run_calibration()


def test_the_labelled_set_is_the_tracked_one(calibration: Dict[str, Any]) -> None:
    """Guards the whole measurement: an agreement statistic computed
    against a set that is not in the repository cannot be re-derived by
    anyone, and the human labels behind it cannot be regenerated."""
    assert PAIRS_PATH.is_file() and LABELS_PATH.is_file()
    total = calibration["constructed"]["pairs"] + calibration["natural"]["pairs"]
    assert 20 <= total <= 30, f"plan §13.3 asks for 20-30 labelled pairs, got {total}"


def test_the_judge_passes_the_pairs_whose_answer_is_not_a_matter_of_taste(
    calibration: Dict[str, Any],
) -> None:
    """The broken-judge detector. One member names the amount the guest is
    approving and the other does not; the author agreed with the
    construction on every one."""
    constructed = calibration["constructed"]
    assert constructed["comparable"] > 0, "every constructed pair was a tie"
    assert constructed["agreement"] >= CONSTRUCTED_FLOOR, (
        "the judge disagrees with the author on a pair whose answer "
        f"follows from its construction: {constructed}"
    )


def test_the_natural_agreement_is_reported(calibration: Dict[str, Any]) -> None:
    """No threshold on the first run, deliberately -- §14's revision rule
    is that a threshold starts from the measured baseline. What this test
    enforces is that the number EXISTS and rests on real comparisons, so
    it can never be quoted without one."""
    natural = calibration["natural"]
    assert natural["comparable"] >= 10, (
        "too few comparable natural pairs to report an agreement figure: " f"{natural}"
    )
    assert natural["agreement"] is not None
    assert Path(
        calibration["result_path"]
    ).is_file(), "the statistic was reported with no artefact behind it"


def test_the_judge_is_not_answering_at_random(calibration: Dict[str, Any]) -> None:
    """The one a-priori bar on the natural pairs, and it is deliberately
    weak: a judge at or below chance on pairwise preference carries no
    information at all, whatever its scores look like. This is not the
    quality bar -- it is the floor below which the judge should not be
    used."""
    natural = calibration["natural"]
    assert natural["agreement"] > 0.5, (
        "the judge agrees with the author no more often than a coin "
        f"would: {natural}"
    )
