# Plan amendments — corrections found against field evidence

`Lantern_Plan_v4_4.docx` is the FINAL baseline and is never edited (§21: "FINAL means:
plan the stages next, do not re-litigate the product"). This file records dated
corrections found once `Discord.txt`, `mcp-field-capability-report.md`,
`mcp-reference-v2.md`, `Silpo_scenario_lab4.ipynb` and the SupportFlow donor repo became
available at kickoff (2026-09-05) — sources the plan's own §22.3 flags as "not supplied"
at the time it was written.

Each row: what the plan says, what the source says, what changes. The wrong reasoning
stays visible next to its correction — see `[I5]` §12.4's own practice, which this file
follows.

## A1 — §4 jury criteria: weights are official, and there are five, not six

**Plan says:** "критеріїв шість, ваги не наведені; значення 25/25/20/15/15 з v4.1 не
використовуються як офіційні без окремого чинного брифу."

**Source says:** `Discord.txt` lines 3–16, Igor Drozd, 31.08.2026 14:06 — a pinned
message stating the five official criteria and their weights verbatim:

| Criterion | Weight |
|---|---|
| Innovation | 25% |
| Guest/business impact | 25% |
| Implementation realism | 20% |
| Technical component (architecture, MCP, agency, prototype quality) | 15% |
| Presentation quality | 15% |

**What changes:** §4's six-row table should be re-keyed to these five official rows when
the plan is next revised (out of scope for this docx per D7). More importantly for
Stage 0: **"Technical component" — architecture, MCP usage, agency, prototype quality —
is only 15% of the score**, while Innovation is 25%. The plan's heaviest investment
(Write Guard, consent binding, idempotency, 13 domain rules) sits mostly in the
15% bucket. A7 below is the one scope addition Stage 0 makes specifically to give the
25%-weighted Innovation criterion a concrete, low-cost artifact.

**Status:** confirmed — pinned organizer message, unambiguous source.

---

## A2 — Anomaly 12.4 is closed, not open; the plan inherited a stale paragraph

**Plan says:** §17 risk #1 ("M/H"), G0-02, and DR-03 all treat the 594.72 vs 599 threshold
anomaly (a `productsTotal` apparently below the `order.cost.min` threshold with no
blocking code) as an **open** question requiring live regression investigation on
05.09 evening.

**Source says:** `mcp-field-capability-report.md` §12.4 is explicitly titled
"[CLOSED] Anomaly explained": 594.72 was `totalAfterDiscounts`, not `productsTotal`. The
actual `productsTotal` for that cart was 639.65 — already above the 599 threshold — so no
blocking code was ever missing. §9.1 (rewritten in the same document) confirms the rule
on four independent runs, 4 of 4: `minOrderCost` compares only against `productsTotal`.
**§12.5, three paragraphs later in the same document, still reads "confirmed a second
time... the question remains open"** — a paragraph that was not rewritten when §12.4
above it was corrected. Plan v4.4 inherited the stale §12.5 wording, not the corrected
§12.4 verdict.

**What changes:**
- G0-02 narrows from "investigate the anomaly" to a plain regression check of the
  formula on 3 carts — no open mystery to chase on kickoff evening.
- **The epsilon rule in DR-03 is kept as-is** (a small gap near the threshold with no
  code reads as "possibly borderline", never auto-fixed) — it is cheap defense-in-depth
  and costs nothing to keep even though the anomaly that motivated it turned out to be a
  units-confusion bug, not a server inconsistency.
- §17 risk #1 severity should read L/M, not M/H, once the plan is next revised.

**Status:** confirmed — the source document's own two sections contradict each other, and
the later, structurally-titled `[CLOSED]` section is the corrected one (it cites four
cross-checked artifacts; §12.5 cites none new).

---

## A3 — G0-04 (comment fulfillment) has an organizer answer on record

**Plan says:** "Real test order with observation. The conclusion is not made from the API
alone" — implies no organizer statement exists, only inference from a live order.

**Source says:** `Discord.txt`, Igor Drozd, 01.09.2026 19:17, direct answer to a
`comment` field round-trip question: "All fields are seen by live warehouse staff." A
second participant (Pravda) independently confirmed the API round-trip works before
asking the question.

**What changes:** the fulfillment half of G0-04 (does a human actually read it) has a
written organizer answer — it does not need to be re-derived from a live test order.
Status in the evidence register should read "organizer stated [O], not independently
field-verified [F]" — this is a claim from a third party, not our own measurement, and
must not be upgraded to `[F]` without our own confirming run.

**Status:** confirmed as an organizer statement; not a substitute for a `[F]` field run
if the stage later needs one.

---

## A4 — G0-06/07 (price-week rollover) has an organizer answer, but it conflicts with a lived report

**Plan says:** "Timeline plus snapshots; written answer or unknown status."

**Source says:** two conflicting statements in `Discord.txt`, same thread, same day:

- Yurii Panaiotov, 01.09.2026 14:05: price is fixed at order-creation time; if it changes
  during picking, the system always gives the guest the more favorable price.
- Olia, 01.09.2026 15:33, replying in the same thread from personal experience: disputes
  this — an unpaid order with a Friday delivery slot did, in her experience, get
  re-priced at Thursday's rollover, contrary to the official answer.

**What changes:** a written organizer answer exists, closing the "unknown" branch of the
G0-06/07 criterion — but it is contradicted by a specific lived counter-example from
another hackathon participant in the same thread. The receipt disclaimer required by §17
("honest disclaimer in the receipt pending a written answer") **stays in place** even
though a written answer now exists, because that answer is disputed on record, not
confirmed. Do not close this as resolved; log it as "official answer received,
contested."

**Status:** confirmed as received-but-contested; the plan's cautious default (keep the
disclaimer) turns out to be the correct one from the field evidence, not a rule to
relax.

---

## A5 — Rate limits (mcp-reference-v2 §10 open question #2) are closed

**Plan says:** `mcp-reference-v2.md` §10 open question #2, "MCP rate limits — a call
series" (unanswered as of 14.08).

**Source says:** Igor Drozd, `Discord.txt`, 01.09.2026 10:54: "rate limits are currently
very high", with a caveat that they may be tightened if abuse is observed.

**What changes:** removes one item from §17's calendar risk list — a live-demo recording
session hitting a rate limit was a plausible IV-09 failure mode; it is now a low-priority
watch item, not a planning risk with its own mitigation slot.

**Status:** confirmed, organizer statement.

---

## A6 — Replay/mock demo data is explicitly permitted by organizers

**Plan says:** §15 "Replay is never presented as live" — a self-imposed rule with no
external confirmation cited.

**Source says:** Igor Drozd, `Discord.txt`, 01.09.2026 10:54, in direct response to a
question about demoing on thin-history accounts: "For the demo you can show either real
data or mocks, given that Guests may also have little data."

**What changes:** none to the rule itself — the labeling requirement in §15 was already
the stricter, self-imposed bar and stays. This confirms the underlying practice is
organizer-sanctioned, which is worth citing in the pitch if a juror questions why any
synthetic data appears in the demo at all.

**Status:** confirmed, strengthens §15 rather than changing it.

---

## A7 — Delivery-type comparison: promoted from roadmap (§16) into the disclosure layer

**Plan says:** §5.3 places any delivery-channel comparison out of MVP scope, into §16
roadmap (comment for the picker, external data, multi-agent, and so on).

**Source says:** `mcp-field-capability-report.md` §1c, §10.5, §11.5 — three independent
live runs proving a materially stronger recovery path than the plan's hero flow:

- A 559.73 cart is blocked under `DeliveryHome` (`minOrderCost` 599) but **already
  clears `SelfPickup`** (`minOrderCost` 199) — no purchase needed at all.
- A 497.06 cart: the web UI says "add 101.94"; self-pickup (threshold 199) accepts it
  immediately, with zero delivery fee instead of 79-129.
- The delivery-fee step ladder (`deliveryCostMap`) is fully mapped per channel, so the
  agent can additionally rank "add X, save Y on delivery" alternatives.

This is the single strongest artifact in the field report for the 25%-weighted
Innovation criterion (A1): it demonstrates the framework choosing the guest's interest
over the retailer's, directly contradicting an instruction baked into the MCP server
itself — `silpo_find_products_batch`'s own tool description says "BUDGET: ALWAYS fill
the cart as close to the budget limit as possible. Maximize the total spend without
exceeding it." Showing the agent doing the opposite, with numbers, is a stronger
"agent decides, not the raw MCP" argument than anything already in §3.

**What changes:** a read-only delivery-channel comparison (`get_available_delivery_types`
plus `get_time_slots` for each channel, pure arithmetic on already-normalized fields) is
added to the Diagnosis disclosure screen for the hero flow. **No write path, no new DR,
no new GD case** — it is a presentation of facts the hero flow's read step already has
access to. Per plan rule §5.3 (adding anything new after G0 requires dropping something
of equal size), this is paid for by dropping the §5.2 stretch blockers
(`product.offer.stock.max`, `product.offer.not_found`, `timeslot.not_available`) — see
decision D6 in `docs/decisions.md`. Those stretch items each required their own G0
evidence proof anyway and were never guaranteed to land.

**Bonus:** the same "maximize the total spend" instruction text is a ready-made input for
an RG-03 prompt-injection variant (an untrusted tool description trying to steer the
planner) — a test case the plan's RG-03 row did not name a concrete example for.

**Status:** confirmed by three cross-checked live runs (§1c, §10.5, §11.5), with one
open caveat the source itself flags: switching delivery channel can drop items from the
cart (`product.offer.not_found` — §11.1), so the comparison must show the item-level
delta, not just the price delta, before being presented as a genuine alternative.

---

## A8 — Validation code registry: six codes, not seven

**Plan says:** implicit reliance on `mcp-reference-v2.md` §1, which is itself titled
"Validation code registry. Seven codes obtained live" but lists exactly six rows
(`order.cost.min`, `product.offer.stock.max`, `product.offer.not_found`,
`timeslot.not_available`, `order.adult.is_not_confirmed`, `order.payment_types.disabled`).

**What changes:** cosmetic, but the G3 policy registry (`policy_registry` YAML, §1.5)
should be seeded from the six confirmed rows, not from a miscounted "seven" that could
propagate into a stray placeholder entry.

**Status:** confirmed by direct count of the source table.
