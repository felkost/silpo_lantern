"""the judges' rubric is code in this repository, not text a
model writes for itself at run time.

DeepEval will happily take a one-line `criteria` and generate its own
evaluation steps. That makes the rubric an artefact of whichever judge
model is configured on the day, silently re-invented when the model
changes -- and a calibration statistic measured against one generated
rubric says nothing about the next one. `judges.py` writes the steps out,
so a change to what the judge rewards is a diff someone reviews.

This module deliberately imports NO deepeval: `import deepeval` calls
`load_dotenv()` and leaks the real `.env` into `os.environ`, which is why
the plugin is disabled outside `make eval` and why
`tests/unit/test_env_isolation.py` exists. Constructing a real metric is
therefore the live tests' job; what belongs in the gate is the rubric
itself and the refusal of an unknown name, both of which are reachable
without the import.
"""

import pytest

from src.lantern.evals.judges import (
    JUDGE_STEPS,
    _BOUNDARY,
    build_judge,
)

PLAN_JUDGES = {
    "RecoveryExplanationQuality",
    "UserControlAndConsentClarity",
    "UncertaintyAndRefusal",
}


@pytest.mark.parametrize("name", sorted(PLAN_JUDGES))
def test_every_judge_carries_the_correctness_boundary(name: str) -> None:
    """The boundary is stated to every judge, not only to the one whose
    subject makes it obvious. A judge that quietly starts rewarding right
    arithmetic is a second opinion competing with a proof."""
    assert _BOUNDARY in JUDGE_STEPS[name], (
        f"{name} does not tell the model to leave arithmetic, "
        "authorization and whether the write happened alone"
    )


@pytest.mark.parametrize("name", sorted(PLAN_JUDGES))
def test_the_rubric_is_written_out_not_generated(name: str) -> None:
    steps = JUDGE_STEPS[name]
    assert len(steps) >= 4, (
        f"{name}'s rubric is thin enough that DeepEval would be filling "
        "in the rest of the judgement itself"
    )


def test_an_unknown_judge_name_is_refused_before_any_import() -> None:
    """`build_judge` validates the name first, so this raises without
    deepeval ever being imported -- which is what lets the check live in
    the gate."""
    import sys

    with pytest.raises(ValueError, match="unknown judge"):
        build_judge("HelpfulnessOverall", model=None)

    assert "deepeval" not in sys.modules, (
        "importing deepeval leaks .env into os.environ -- the gate must " "not do it"
    )
