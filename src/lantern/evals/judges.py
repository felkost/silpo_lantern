"""the three offline DeepEval judges, and the boundary they
are not allowed to cross.

Plan §13.3 names three: `RecoveryExplanationQuality`,
`UserControlAndConsentClarity`, `UncertaintyAndRefusal`. All three score
the guest-facing SENTENCE and nothing else.

**The boundary, and why it is a boundary rather than a preference.** A
judge must never score arithmetic, authorization, or whether a write
happened. Those are decided by pure code and proved by an independent
read-back (`CLAUDE.md`'s third and fourth invariants); a model that also
graded them would be a second, weaker opinion competing with a proof, and
the project's own rule is that money and post-conditions are never the
model's to judge. Stated in every criterion below AND enforced by T22,
which feeds each judge pairs differing only in a correctness-adjacent
dimension and fails if the scores move.

**Where the line actually falls**, because it is finer than it first
looks: a judge must not care *whether the write succeeded*, but it must
care *whether the sentence tells the guest the truth about it*. "The
write failed" is a fact for code to establish. "The sentence claims a
success that was never confirmed" is a property of the text, and
`UncertaintyAndRefusal` exists to catch exactly that. T22's pairs hold
the text's claims fixed and vary only the underlying fact.

`evaluation_steps` rather than a bare `criteria`: DeepEval generates its
own steps from a criteria string, which makes the rubric a thing the
judge model invents at run time and quietly re-invents when the model
changes. Written out here, the rubric is versioned with this file.
"""

from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:  # pragma: no cover - typing only
    from deepeval.metrics import GEval

_BOUNDARY = (
    "Do not reward or penalise whether the arithmetic is right, whether "
    "the write was authorized, or whether the change actually happened. "
    "Those are settled elsewhere and are not yours to score. Judge only "
    "what the sentence says and how it says it."
)

QUALITY_STEPS: List[str] = [
    "Read the text as a Ukrainian-speaking shopper would.",
    "Reward natural, idiomatic Ukrainian: correct declension of product "
    "names, correct agreement of numerals with the nouns they count, and "
    "units written the way a Ukrainian shop writes them.",
    "Penalise russianisms, surzhyk, and constructions calqued from "
    "Russian or English, however fluent the sentence otherwise reads.",
    "Penalise a text that is harder to follow than the situation "
    "requires -- padding, hedging that says nothing, or a wall of detail "
    "where one sentence would do.",
    _BOUNDARY,
]

CONSENT_STEPS: List[str] = [
    "Ask what a guest would know, from this text alone, about what they "
    "are being asked to approve.",
    "Reward a text that names the specific thing that will change and "
    "the amount it will change by, so the guest can decide before "
    "anything happens.",
    "Penalise a text that asks for agreement while leaving the guest to "
    "guess what changes, by how much, or to what.",
    "Reward wording that leaves the decision with the guest. Penalise "
    "wording that presses, hurries, or presents the change as already "
    "settled.",
    _BOUNDARY,
]

UNCERTAINTY_STEPS: List[str] = [
    "Ask whether the text's own claims are ones the text is entitled " "to make.",
    "Reward a text that says plainly what is not known or could not be "
    "confirmed, and that names what it did not do.",
    "Penalise a text that claims a result as established when it "
    "presents no basis for it, or that reports a refusal as though it "
    "were a success.",
    "Reward a refusal that tells the guest what they can do next. "
    "Penalise one that merely apologises, or that hides the refusal in "
    "vague language.",
    "This is about the TEXT'S CLAIMS, not about what really happened: "
    "judge whether the sentence overstates its own footing, never "
    "whether the underlying operation succeeded.",
    _BOUNDARY,
]

JUDGE_STEPS = {
    "RecoveryExplanationQuality": QUALITY_STEPS,
    "UserControlAndConsentClarity": CONSENT_STEPS,
    "UncertaintyAndRefusal": UNCERTAINTY_STEPS,
}


def build_judge(name: str, model: Any, threshold: float = 0.5) -> "GEval":
    """One GEval metric by name, bound to an already-built model.

    `model` is injected, never constructed here -- the same "inject the
    boundary, don't build it inside" rule `OpenRouterJudge` follows, so a
    caller can pass a fake and exercise this module with no network.
    """
    # Validated BEFORE the import: `import deepeval` calls `load_dotenv()`
    # and leaks `.env` into `os.environ` (the reason the plugin is
    # disabled everywhere but `make eval`, and `tests/unit/
    # test_env_isolation.py` pins it). A caller checking a name must not
    # pay that side effect, and the gate must be able to exercise this
    # branch without importing deepeval at all.
    if name not in JUDGE_STEPS:
        raise ValueError(
            f"unknown judge {name!r}; expected one of {sorted(JUDGE_STEPS)}"
        )

    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    return GEval(
        name=name,
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        evaluation_steps=list(JUDGE_STEPS[name]),
        model=model,
        threshold=threshold,
        async_mode=False,
    )


def score_text(metric: Any, text: str) -> float:
    """Scores one guest-facing sentence.

    `input` is a fixed constant, not the situation that produced the
    text: two members of a calibration pair must differ ONLY in the
    sentence being judged, and feeding each its own context would let the
    context, rather than the writing, move the score.
    """
    from deepeval.test_case import LLMTestCase

    metric.measure(
        LLMTestCase(
            input="Guest-facing message from the recovery agent.", actual_output=text
        )
    )
    return float(metric.score)
