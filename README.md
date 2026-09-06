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

Infrastructure and domain core complete. The API starts, runs its database migrations
and opens a pooled LangGraph checkpointer against Postgres; the MCP adapter has a
dynamic `tools/list` registry with drift detection, a typed error hierarchy and OAuth
token storage; the fixture pipeline and its schemas exist.

The domain core is built and tested against a real cart read from the live Silpo MCP
server: the normalizer (money as `Decimal`, coordinates as `float`, `null` never
coerced to zero), the domain rules, the diagnosis with an exact gap computed by code
rather than by a model, the policy registry with a fail-safe for validation codes it
does not recognise, and the read-only disclosure layer including the delivery-channel
comparison. It does no I/O at all — an architecture test enforces that, and the whole
of it runs offline.

The agent graph, the planner and the recovery UI are the next stages. The write path is
deliberately unreachable until the Write Guard is built: no code in this repository can
change a cart today.

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

The registry treats the server as untrusted input: it caches the tool list with an
expiry, invalidates immediately on a protocol or schema error, rejects an oversized
response before processing it, and flags any tool name absent from the previous
snapshot instead of accepting it as usable.

## Running it

Copy `.env.example` to `.env` and fill in `DATABASE_URL` (a Postgres connection string in
the `postgresql+psycopg://` form) before the first run.

```
make run                # start the API: migrations, checkpointer, GET /health
make gate               # black + flake8 + mypy + unit and contract tests, no network
make test-integration   # tests that need a reachable Postgres; skipped without DATABASE_URL
make openapi            # dump the generated OpenAPI 3.1 schema
make report             # regenerate the architecture page
make secret-scan
```

`make run` invokes `python -m apps.api` rather than `uvicorn` directly: on Windows uvicorn
selects an event loop that the async Postgres driver refuses, and the launcher is what
fixes it.

## Tests

`tests/unit/` and `tests/contract/` are the commit gate: pure, offline, no network, no
database — `pytest` there makes no live call of any kind. `tests/integration/` needs a
real Postgres and runs only via `make test-integration`; each of its tests skips itself
with a clear reason when `DATABASE_URL` is unset. `tests/smoke/`, `tests/e2e/` and
`tests/evals/` (DeepEval-based, run separately and never in the commit gate) are
populated by later stages.

## Metrics

Recovery completion rate, median time-to-recovery vs. the app, actions-to-recovery,
disclosure rate, and a hard 0% gate on unauthorized writes / false recovery — reported
with sample size, never as a bare number. None of them are measured yet; that begins
once the agent runs end to end. See
[`docs/reports/index.html`](docs/reports/index.html), which explains how the parts
interact and why that is expected to help.

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
