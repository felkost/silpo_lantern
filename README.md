# Lantern — Checkout Transparency Agent for Silpo

**Ліхтарик** in the Ukrainian UI and pitch. When a guest's Silpo cart is blocked by a
checkout rule, Lantern reads the live cart through Silpo's official MCP server, surfaces
every validation the cart already carries — including ones the app's own screen never
renders — computes the exact gap to checkout, proposes 2–3 relevant products, and, only
after the guest's explicit consent to one specific plan, performs the minimal cart change
and proves the outcome by reading the cart back. Checkout and payment stay the guest's
own action, always.

See [`docs/reports/index.html`](docs/reports/index.html) for the architecture diagrams,
the hero recovery flow, the safety state machine, and the business-value argument behind
this project.

## Status

Scaffold stage. Application code (MCP client, domain rules, agent graph, UI) has not
been written yet — only the repository structure, the commit gate, and a layering test
enforcing the architecture described in the report above exist so far.

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
("before → after", not a bare "success"). See the sequence diagram in
[`docs/reports/index.html`](docs/reports/index.html).

## MCP tools

Official endpoint `https://mcp.silpo.ua/mcp`, OAuth 2.1 + PKCE, discovered dynamically
via `tools/list` at session start — never a hardcoded tool count. Read tools are
model-chosen inside the planning step; the single write tool is authorized by a
dedicated Write Guard node, never by the model.

## Running it

Not yet runnable — `make run` prints which stage adds it. Available commands: `make gate`
(lint + test), `make test`, `make lint`, `make secret-scan`, `make report` (regenerates
the architecture page).

## Tests

`tests/unit/` (pure, no network), `tests/contract/`, `tests/integration/`,
`tests/smoke/`, `tests/e2e/`, `tests/evals/` (DeepEval-based, run separately from the
commit gate).

## Metrics

Recovery completion rate, median time-to-recovery vs. the app, actions-to-recovery,
disclosure rate, and a hard 0% gate on unauthorized writes / false recovery — reported
with sample size, never as a bare number. See section 5 of
[`docs/reports/index.html`](docs/reports/index.html) for current status.

## Privacy

Secrets and OAuth tokens live in backend `.env` only, never in the client or the
repository — enforced by `make secret-scan` and CI. Fixture data is sanitized before it
reaches the repository or CI; raw captures never leave the local machine.

## Limitations

MVP scope is a single hero recovery flow (a blocked cart's minimum-order-sum rule) plus a
read-only comparison across delivery channels. No autonomous checkout, payment, or age
confirmation. No second chat interface, no runtime web search.

## License

See [`LICENSE`](LICENSE).
