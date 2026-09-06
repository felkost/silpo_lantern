# eval_judge — v1

**Model:** cross-vendor to the planner (`google/*`) to limit self-preference
bias. Candidates in `config/models.yaml`'s `eval_judge.candidates`:
`x-ai/grok-4.6` or `anthropic/claude-opus-5`; selection is a
cost/availability decision, not a language-quality one — either candidate
is cross-vendor to the planner.

**Prompting technique:** zero-shot, rubric-anchored scoring. The rubric
itself (grammar / naturalness / term accuracy, 1-5 each, plus a binary
critical-error flag for surzhyk/Russianisms) is written into this prompt
BEFORE any model is scored, so the rubric cannot be shaped by having
already seen one candidate's output.

**Scope, stated honestly (this stage's own limitation):** this prompt is
used ONLY for UA-Eval candidate selection — picking which model becomes
`explainer`. It is explicitly **not calibrated** against a labelled set
this stage (`config/models.yaml`'s `eval_judge.calibrated: false`) —
judge agreement metrics (Cohen's kappa and the paradox under skew) are a
later stage's job. A judge score from this prompt should not be read as
more authoritative than what it actually is: one model's rubric-guided
opinion, cross-checked by the mandatory manual review of 10 responses per
candidate that this stage does not skip in favor of trusting the judge
alone.

## Unit economics (author-requested design constraint, not in the plan text)

Called once per (explainer-candidate × UA-Eval prompt) pair — up to
4 candidates × 25-30 prompts = up to 120 calls, the largest call VOLUME in
this stage even though each individual call is small (one explainer
response to score, not a whole session). The cost estimate ($1.3/$4.4
depending on Grok vs. Opus) is dominated by this multiplication, not by
any single call's size — which is exactly why the manual-review step is
capped at 10 responses per model rather than all 25-30: the judge scores
everything, a human spot-checks a bounded sample.

## Input contract

- One UA-Eval prompt (from `datasets/ua-eval-v1.0.0/`, not yet built this
  stage's implementation — the actual dataset file is a separate
  deliverable)
- One candidate model's response to that prompt

## Output contract

```json
{
  "grammar": 4,
  "naturalness": 5,
  "term_accuracy": 4,
  "critical_error": false,
  "critical_error_note": ""
}
```

All three numeric fields 1-5. `critical_error` is a hard boolean — the
selection rule requires ZERO critical errors regardless of how high the
numeric scores are; a 5/5/5 response with one surzhyk word still fails
the selection rule.

## Content

```
You are scoring one Ukrainian-language response from a candidate model
against a fixed rubric, for a grocery checkout-assistant explanation task.
Score independently of how fluent or confident the response sounds —
grammar, naturalness, and term accuracy are separate axes; a confident but
grammatically wrong response scores low on grammar regardless of tone.

grammar (1-5): correct case, gender, number agreement; correct verb
conjugation (e.g. "бере"/"береш", never "беруш"/"береш").
naturalness (1-5): reads as something a Ukrainian speaker would actually
say, not a stilted or overly literal construction.
term_accuracy (1-5): correct handling of numerals, currency, units, and
package sizes (г/кг/шт/пачка); correct declension of the product name.
critical_error (boolean): true if the response contains surzhyk, a
Russianism, or a factual number that does not match the one given in the
prompt — set true even if the numeric scores above are otherwise high.

Prompt given to the candidate: {ua_eval_prompt}
Candidate response: {candidate_response}

Output only the scoring JSON — no prose.
```

**Version notes:** v1. No live model has been run against this text yet —
the UA-Eval run is the first live use.
