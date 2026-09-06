# recovery_planner — v1

**Model:** `google/gemini-3.8-flash` (config/models.yaml) — chosen for
reliable structured output and tool-choice at a low price. Its own
language criterion is soft: this prompt's output is JSON, never shown to
the guest.

**Prompting technique:** zero-shot, schema-constrained structured output.
No few-shot examples — the task (turn a diagnosis into search terms) is
narrow and low-ambiguity; examples would cost tokens without reducing
variance on a task this constrained. No chain-of-thought: all arithmetic
(gap, thresholds, channel comparison) is already computed by domain code
before this prompt ever runs — asking the model to "think through" numbers
it must never touch would invite exactly the hallucination that
authorizing writes only from pure code exists to prevent.

## Unit economics (author-requested design constraint, not in the plan text)

This is the **infrequent, context-heavy** call in the graph — once per
recovery session, not once per candidate. The cost model sizes it at
**~30K input tokens, ~4K output tokens** ($0.0375/call at the current
price) — an order of magnitude more input than `explainer_v1.md`'s ~6K,
because this prompt carries the full diagnosis + disclosure + 3-row
channel comparison, while the explainer receives one already-decided
candidate at a time.

**No conversation history is fed into this prompt, ever.** State that
matters (owner, constraints, action_id, expiry) lives in
`RecoveryState`/Neon, never in an accumulated chat log — what was lost is
not reconstructed by guessing, and consent is never restored from an
LLM summary. Each call is built fresh from the current `RecoveryState`,
not from what a previous call said. This keeps input size bounded by the
diagnosis's own size, not by how many turns the session has had — a model
with a 32K-128K context window comfortably covers the ~30K figure above
with room for the tool schemas in `tool_view.py`'s planner view; a
smaller-context model would need re-measuring against the real payload
before use, not assumed to fit.

## Input contract

The node receives (never raw MCP responses, never a tool description):

- `Diagnosis` (blockers, gap, primary code) — already computed
- `DisclosureReport` — all validations, including UI-invisible ones
- `list[ChannelComparisonRow]` — the 3-channel comparison (A7)
- `list[PlannerVisibleTool]` (`tool_view.build_planner_tool_view`) — name +
  reviewed paraphrase + JSON Schema only, for the 7 tools this stage uses

## Output contract

Bound to `src.lantern.graph.schemas.SearchIntent` — checked structurally
(`tests/unit/test_planner_schema_carries_no_evidence_shaped_fields.py`) to
carry no `product_id`/`price`/`availability`-shaped field:

```json
{
  "search_terms": ["молоко", "хліб"],
  "quantity_hint": 1,
  "note": ""
}
```

`search_terms`: 1-5 short strings, product names or categories relevant to
clearing the gap in the guest's own existing branch/delivery context —
never article codes invented by the model (an `externalProductId` is a real
fact from a live catalogue lookup, not something to guess at here).

## Content

```
Given the diagnosis, disclosure, and channel comparison below, propose 1-5
short search terms for products that could help clear the blocking gap —
relevant to what the guest's cart already contains, in the same branch and
delivery context. Prefer terms close to items already in the cart (e.g. if
the cart has dairy, suggest another dairy item) over generic filler.
Suggest the minimum plausible quantity — never suggest more than needed to
plausibly clear the gap. Output only the SearchIntent JSON — no prose, no
explanation, no markdown.

Diagnosis: {diagnosis_json}
Disclosure: {disclosure_json}
Channel comparison: {channel_comparison_json}
Available tools (for your own awareness only — you do not call them; a
later step does): {planner_tool_view_json}
```

**Version notes:** v1. No live model has been run against this text yet —
the first live use is still ahead, after which this file gains a
"measured" section with real token counts and any prompt revision the
live run's own output shows is needed.
