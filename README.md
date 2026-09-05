# Lantern — Checkout Transparency Agent for Silpo

**Ліхтарик** in the Ukrainian UI and pitch. When a guest's Silpo cart is blocked by a
checkout rule, Lantern reads the live cart through Silpo's official MCP server, surfaces
every validation the cart already carries — including ones the app's own screen never
renders — computes the exact gap to checkout, proposes 2–3 relevant products, and, only
after the guest's explicit consent to one specific plan, performs the minimal cart change
and proves the outcome by reading the cart back. Checkout and payment stay the guest's
own action, always.

## Status (as of 2026-09-05, Stage 0)

**Scaffold only. No application code exists yet — this is deliberate.** Stage 0
(kickoff) builds the repository structure, the commit gate, branch protection, and the
evidence-lab notebook, so that G0 (05.09 evening) and G1+G2 (06.09) can start writing
actual domain code against a repository whose rules are already settled. See
`docs/decisions.md` and `handoff.md` for exactly what is and is not built.

| Area | Status |
|---|---|
| Repository scaffold, layer table, commit gate | done |
| Layering test + 5 declared-failing domain rule tests | done (intentionally failing) |
| Evidence lab notebook (G0) | done, requires the user's own MCP OAuth session |
| MCP client, domain core, agent graph, UI | not started |
| Live demo, evaluation, submission | not started |

## Problem

A guest fills a cart, checkout is blocked by a domain rule (minimum order sum, an
unavailable item, an unconfirmed age check). The app's screen shows one message; the MCP
server's own response often carries more structured detail than the screen displays. The
gap between what is known and what is shown is a plausible cause of abandoned purchases —
not yet measured, and not overstated here.

## User

Primary: an authenticated Silpo guest with an active, blocked cart. Secondary: Silpo's
e-commerce team (fewer abandoned carts, fewer support contacts, visibility into why
checkouts fail).

## Agent flow

Read (`tools/list` discovery, then the cart) → diagnose (all validations, not just
blockers) → plan (LLM proposes candidates, backed only by live MCP evidence) → explicit
consent (bound to one action, one state) → re-read (state may have changed) → guarded
write (one allowed tool, one node) → read-back (independent proof) → receipt
("before → after", not a bare "success"). Full contract: plan §6.

## MCP tools

Official endpoint `https://mcp.silpo.ua/mcp`, OAuth 2.1 + PKCE, discovered dynamically
via `tools/list` at session start — never a hardcoded tool count. Read tools are
model-chosen inside the planning step; the single write tool is authorized by a
dedicated Write Guard node, never by the model. See `CLAUDE.md` §4 for the invariants
this enforces.

## Running it

Not yet runnable — `make run` prints which gate adds it. See `Makefile` for the current
commands (`make gate`, `make test`, `make lint`, `make secret-scan`, `make report`).

## Tests

`tests/unit/` (pure, no network), `tests/contract/`, `tests/integration/`,
`tests/smoke/`, `tests/e2e/`, `tests/evals/` (DeepEval, gated separately). See
`CLAUDE.md` §7.

## Metrics

Recovery completion rate, median time-to-recovery vs. the app, actions-to-recovery,
disclosure rate, and a hard 0% gate on unauthorized writes / false recovery. Definitions:
plan §13.

## Privacy

Secrets and OAuth tokens live in backend `.env` only, never in the client or the
repository — enforced by `make secret-scan` and CI. Fixture data is sanitized before it
reaches the repository or CI; raw captures never leave the local machine
(`datasets/fixtures/raw/` is gitignored). See `docs/task-lantern-plan-v4-4.md` §12.1.1.

## Limitations

MVP scope is the `order.cost.min` hero flow plus a read-only delivery-channel comparison
(see `docs/plan-amendments.md` amendment A7). No autonomous checkout, payment, or age
confirmation. No second chat interface, no runtime web search. Full boundary:
`docs/requirements-checklist.md`.

## Further reading

- `docs/task-lantern-plan-v4-4.md` — the verbatim product plan (Ukrainian)
- `docs/plan-amendments.md` — corrections found against field evidence
- `docs/decisions.md` — numbered kickoff decisions
- `docs/requirements-checklist.md` — the literal requirement checklist
- `docs/reports/index.html` — stage-by-stage evidence appendix
- `BACKGROUND_MATERIALS.md`, `AI_USAGE.md`, `THIRD_PARTY_NOTICES.md`
