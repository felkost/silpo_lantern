"""Structured-output contracts for the two LLM nodes (`plan`, `explain`).
Neither schema carries a price/productId/availability-shaped field — this
is what makes a hallucinated `EvidenceTuple` structurally impossible to
construct from an LLM's own output type, not merely a convention nobody
violates by accident.
"""

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class SearchIntent(BaseModel):
    """The planner's ENTIRE output. No node downstream of `plan` reads
    anything from this model except `search_terms`/`quantity_hint` — in
    particular, `collect_options` never trusts a price or an id from here,
    because none exists to trust.
    """

    model_config = ConfigDict(frozen=True)

    search_terms: List[str] = Field(min_length=1, max_length=5)
    quantity_hint: int = Field(default=1, ge=1, le=10)
    note: str = ""


class ExplainerOutput(BaseModel):
    """The explainer's entire output: one guest-facing UA sentence per
    `ActionProposal`. Carries no money field of its own — the number the
    guest sees is `ActionProposal.expected_delta`, already computed by
    `rank_candidates`/the Evidence Gate before this node ever runs; the
    explainer narrates a value it did not calculate.
    """

    model_config = ConfigDict(frozen=True)

    action_id: str
    guest_text_uk: str = Field(min_length=1)


class EvalJudgeScore(BaseModel):
    """UA-Eval's judge output contract (see `prompts/eval_judge_v1.md`'s
    own "Output contract" section) — three 1-5 rubric axes plus a hard
    boolean that overrides them: the selection rule requires ZERO critical
    errors regardless of how high the numeric scores are.
    """

    model_config = ConfigDict(frozen=True)

    grammar: int = Field(ge=1, le=5)
    naturalness: int = Field(ge=1, le=5)
    term_accuracy: int = Field(ge=1, le=5)
    critical_error: bool
    critical_error_note: str = ""
