# OpenRouter model prices — snapshot 2026-09-05

Source: live `GET https://openrouter.ai/api/v1/models`, queried 2026-09-05 (kickoff).
Every later cost estimate in this project cites this file. Refreshing mid-project is a
new dated file, never an in-place edit — see `/refresh-model-prices`.

Plan §8.5 named these roles and ids on 03.09.2026 pricing. Re-verified against the live
catalogue at kickoff; the plan's own $/1M figures are reproduced next to the live
per-token figures for a sanity cross-check.

| Role (plan §8.5) | Model id (verified live) | Prompt $/1M | Completion $/1M | Context | Plan §8.5 figure |
|---|---|---|---|---|---|
| recovery_planner | `google/gemini-3.8-flash` | 0.75 | 3.75 | 1,048,576 | 0.75 / 3.75 — match |
| recovery_explainer | `google/gemini-3.5-flash-lite` | 0.30 | 2.50 | 1,048,576 | 0.30 / 2.50 — match |
| explainer A/B candidate | `deepseek/deepseek-v4-flash` (live alias resolves to `deepseek/deepseek-v4-flash-0731`) | 0.065 | 0.18 | 1,310,720 | ~0.07 / 0.18 — match |
| eval_judge candidate | `x-ai/grok-4.6` | 2.00 | 6.00 | 500,000 | 2 / 6 — match |
| eval_judge candidate | `anthropic/claude-opus-5` | 5.00 | 25.00 | 1,000,000 | 5 / 25 — match |
| fallback (all roles) | `z-ai/glm-5.3-flash` | 0.075 | 0.25 | 1,310,720 | ~0.08 / 0.25 — match |
| UA-Eval candidate | `qwen/qwen3.8-flash` | 0.15 | 0.47 | 1,000,000 | not priced in §8.5 |

## Notes

- **`deepseek/deepseek-v4-flash` is a live alias**, not a pinned id. The catalogue
  resolves it to the dated snapshot `deepseek/deepseek-v4-flash-0731`. IV-05 must pin the
  dated id in `config/models.yaml`, not the alias — an alias can silently repoint to a
  different weights snapshot between now and the live demo.
- All six plan-named ids exist in the live catalogue and their prices match the plan's
  03.09 figures to the cent. No `«…»` placeholders needed for this table.
- This snapshot was fetched via the WebFetch tool (page-summarization path), not a raw
  JSON dump — IV-05 should re-fetch with a direct API call and store the raw response
  under `docs/evidence/` for the byte-exact record the go/no-go criterion needs.
- Budget arithmetic (hero cost, 250–300 run estimate) is **not** recomputed here — that
  stays in the plan's §8.5 prose until IV-05 fixes the actual token profile. This file
  only pins the price inputs to that arithmetic.
