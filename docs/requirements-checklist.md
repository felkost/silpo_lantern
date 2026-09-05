# Requirements checklist

Verbatim, one line per thing the brief actually demands, in the brief's own words
(translated to English for this checklist file; the source stays Ukrainian in
`docs/task-lantern-plan-v4-4.md`). This is the acceptance criterion for the whole
project. A plan review may reorder, merge, cut, or deepen stages against it; it may
**not** add a requirement the source text does not contain.

Re-derived from `Lantern_Plan_v4_4.docx` §18 (Definition of Done) and §5 (MVP scope) at
kickoff (2026-09-05). Boxes are re-checked against artifacts at every stage close, not
re-read from memory.

## From §18 — Definition of Done

- [ ] Official endpoint `https://mcp.silpo.ua/mcp`; `tools/list` and ≥1 real tool call
      visible in the demo/trace.
- [ ] Tokens and OAuth secrets are backend-only; secret scan and redaction tests pass.
- [ ] Hero `order.cost.min` passes end-to-end: diagnose (with disclosure) → plan →
      consent → guarded write → read-back → receipt.
- [ ] 0 unauthorized writes across the full golden/negative/RG suite; every write has a
      mandatory read-back path; false recovery = 0. Read failure produces `unverified`,
      never a successful receipt.
- [ ] Before/after numbers exist from moderated tests (n=5–8) and a measured disclosure
      rate; every number in the pitch has a carrying artifact.
- [ ] Dynamic schemas; server/release/schema hash and app/prompt/policy/model versions
      appear in the trace.
- [ ] Golden dataset (15 cases) and RG-01…07 variants are versioned; MVP-active gates
      pass. Deterministic CI checks are separate from flagged LLM E2E/DeepEval runs;
      RAG tests activate only with the corresponding option.
- [ ] Test-data package ready: 3–5 sanitized recorded templates or a documented blocked
      status; synthetic/mutated variants with a fixed seed; a manifest with
      origin/schema hash/generator version/transformations; PII/secret scan = 0;
      schema and domain validation pass; raw records absent from repo, CI, and
      submission.
- [ ] A controlled live proof and an explicitly labeled replay fallback both exist.
- [ ] State (consent, idempotency, receipts, checkpoints) lives in Neon Postgres; no
      state depends on service disk.
- [ ] The demo reproduces locally without Render; a public URL exists only if IV-06
      passes; all secrets are backend env vars; the sole paid line item is the
      OpenRouter top-up (plus Starter, if IV-08 decides so).
- [ ] A 3–5 minute video per §15 and a submission package match the official format;
      submission is 2026-09-12 (the 2026-09-14 hard deadline is an untouched reserve).
- [ ] LLM spend ≤ $20, confirmed by the OpenRouter dashboard; every call's model id is
      recorded in LangSmith traces.
- [ ] README covers: problem, user, agent flow, MCP tools, running it, tests, metrics,
      privacy, limitations; plus `AI_USAGE.md`, `THIRD_PARTY_NOTICES.md`,
      `BACKGROUND_MATERIALS.md`.

## From §5.1 — Hero scenario (mandatory)

- [ ] `order.cost.min` blocker: exact gap to the minimum sum
      (`minOrderCost ↔ productsTotal`), 2–3 relevant products in the same
      branch/delivery context, consent to a concrete plan, a cart change via an
      allowed tool, proof by read-back.
- [ ] Disclosure layer: shows all cart validations, including ones invisible in the UI.
- [ ] Absence of `checkoutWebLink` treated as an additional signal, not a universal
      equivalence to "blocked".

## From §5.3 — Explicitly out of MVP scope

- [ ] No second universal chat, no runtime web search, no vector database for
      prices/stock/slots.
- [ ] No autonomous checkout, payment, age confirmation, or other legally significant
      action.
- [ ] No guarantees about comment-to-picker fulfillment or price-week locking without
      evidence (G0-03/04, G0-06/07).

## Amendment note

Amendment A7 (`docs/plan-amendments.md`) adds one read-only item beyond this checklist's
literal source text — the delivery-channel comparison — under plan rule §5.3's own
"drop something of equal size" clause (decision D6). It is recorded as a **decision**,
not inserted into this checklist: the checklist stays verbatim to the brief, and the
decision log is what a future session actually searches for scope changes.
