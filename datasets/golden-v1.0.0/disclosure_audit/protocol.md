# Disclosure audit protocol

The measurement behind `DisclosureRate`, which the brief defines as: sessions carrying at
least one **confirmed-invisible** constraint, over sessions whose visibility was actually
verified. Unknown is never counted as hidden — a session nobody checked leaves both halves
of the fraction.

It is the one metric in this project that cannot be computed from data the system itself
holds. Everything else is decided by re-reading the cart; this one asks what the retailer's
own app *renders*, which only a person looking at a screen can answer.

---

## 1. The visibility boundary

Agreed with the author, 2026-09-10, and fixed before any observation was taken — deciding
it afterwards would let the result choose its own rule.

**Shown** means visible to the guest on either:

- the cart screen, or
- the checkout screen, up to but not including the payment step.

**Not shown** means everything else: a constraint discoverable only by attempting to place
the order, by contacting support, or by reading a response the app never surfaces.

Rationale: these are the two screens a guest passes through while deciding, so a constraint
rendered there had a real chance of being seen. One that only appears after the decision
has been made is not disclosure — it is a failed checkout.

## 2. Blind ordering, and why it is not optional

**The observer records what the app shows BEFORE being told what the cart carries.**

The audit's whole question is whether a person using the app would notice a constraint. An
observer who has been handed the list of validations first is no longer that person: they
will scan for what they were told to find, and a search that succeeds proves nothing about
what an unprompted guest would see.

So each observation runs as:

1. The observer opens the Silpo app on the target cart state and writes down every
   blocking or warning message they can see, in their own words, on both in-scope screens.
2. **At the same time**, the cart is read through `mcp.silpo.ua`
   (`scripts/read_cart_validations.py`, read-only, no writes) and the validation codes it
   actually carries are recorded.
3. Only then are the two put side by side.

Step 2 must happen while the cart is in the state step 1 observed. A cart read an hour
later is a different cart.

## 3. What one row is

One row per **cart state observed**, not per constraint. A state where the cart carries
three validations and the app shows one is a single row with
`had_invisible_constraint: true`.

| Field | Set by | Meaning |
|---|---|---|
| `state_id` | protocol | which of the states in the states table below |
| `observed_at` | observer | when the app was looked at |
| `app_messages` | observer | every message seen, verbatim, in-scope screens only |
| `screens_checked` | observer | which of the two screens were actually opened |
| `cart_validations` | MCP read | the codes the cart carries |
| `visibility_verified` | derived | true only when BOTH in-scope screens were opened and the MCP read succeeded on the same state |
| `had_invisible_constraint` | derived | true when at least one carried validation has no corresponding message |

`visibility_verified` is false — and the row leaves the denominator — whenever the observer
checked only one screen, or the cart moved between the two steps. That is not a wasted
observation; it is an honest one.

## 4. The states

| # | State | Expected in data | How it is reached |
|---|---|---|---|
| 1 | Baseline, `productsTotal` 523.32 | `order.cost.min` **and** `order.payment_types.disabled` — two constraints | nothing to do; the cart is already here |
| 2 | Above the threshold, ~750 | no blocking validations | add items |
| 3 | Lapsed delivery slot | `timeslot.not_found` plus `product.offer.stock.max` on every line | let the booked slot pass without renewing it |
| 4 | One unavailable line | `product.offer.stock.max` on one line | add an item with little stock left |

State 1 is the most valuable and costs nothing: the cart **already** carries two
constraints. If the app renders one, that is this project's own headline claim measured for
the first time rather than asserted.

State 2 is the control. Its job is to catch the opposite error — an app that shows a
warning where the data carries none would make every other row harder to read.

State 3 needs a day to arrive. Record it whenever it happens, as its own dated observation;
do not hold the other three waiting for it.

## 5. Reporting

The result is `n` observations with the count of invisible-constraint sessions, never a
bare percentage. Four observations produce an interval far wider than the estimate, and the
report says so: this is a first measurement with a stated sample size, not a rate that
clears a threshold. `DisclosureRate` stays N/A until at least one row is
`visibility_verified`.

Coverage — how many states were checked at all — is reported beside the rate, per the brief's
own requirement that UI-audit coverage be stated separately.
