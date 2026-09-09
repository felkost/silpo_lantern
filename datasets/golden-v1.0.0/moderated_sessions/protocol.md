# Moderated sessions — protocol (§12.2)

> **DEFERRED, 2026-09-10. Not run, and n = 0.**
>
> **Reason:** the author has no access to 5–8 participants. This is a resource
> constraint stated plainly, not a finding and not a quiet omission.
>
> **Owner:** the author, per D63 — recruitment and facilitation were always human work;
> the protocol, the instruments and the analysis rules were the assistant's part, and
> those are below and complete.
>
> **What would lift the deferral:** access to five or more Ukrainian-speaking people who
> have not seen the prototype. Everything else — the carts, the script, the recording
> fields, the analysis rules — is specified and ready.
>
> **What was NOT done instead, deliberately:** the author did not run the sessions on
> himself. He built the system, so he cannot play a person meeting it for the first time,
> and the protocol's most valuable question — "what exactly did you just approve?" —
> cannot be answered by someone who already knows. Substituting the author would report
> familiarity as comprehension.
>
> **§14's criterion is still met, by its own terms:** it asks that «n і coverage явні» —
> that n and coverage be *explicit* — not that n be large. n = 0 is reported as N/A per
> §13.1's rule, never as 0%. The §15 video script is written from measurements that do
> exist, and is delivered with the stage reports.
>
> The protocol below is kept in full, unchanged. It is what to follow if participants
> become available.

The before/after comparison plan §12.2 asks for: A is the current Silpo app, B is Lantern,
within-subject, counterbalanced, n = 5–8, a 4-minute task limit chosen to sit under the
5-minute consent TTL so a consent cannot expire mid-task.

Design amended by `A-G9-02` (different but comparable carts; the author's account;
sequential sessions).

---

## 1. What these sessions can and cannot establish

**Stated first, because it decides everything below.** At n = 5–8 this is not an
experiment. Elsewhere in this project, 33 observations gave an interval of [0.90, 1.00] and
12 paired comparisons gave [0.31, 0.83]. Six participants cannot establish that one
condition is faster or takes fewer actions: any interval will cover any plausible effect.

Designing these sessions as proof of an advantage would guarantee an honest answer of "we
cannot tell", after spending eight people's time to get it.

**What six people reliably do show**, and what §12.2 itself asks for under «переказ
блокера» and «зрозумілість, контроль і довіра»:

- whether a person understands **what they are approving** before they approve it — the
  question no automated instrument in this project has been able to answer, and the one
  with safety consequences;
- whether they can **restate the blocker** in their own words afterwards, per condition;
- **where they get stuck**, which is qualitative and is what the §15 video needs;
- discrete failures — if five of six cannot finish in A and six of six finish in B, that is
  visible without statistics.

So: time and actions are **recorded and reported per participant as paired differences**,
never averaged into a claim of time saved. §13.4's rule applies unchanged — an unfinished
task stays in the completion count with its time marked censored, and paired differences
are computed only over pairs completed in **both** conditions, with the number of such
pairs stated.

## 2. The two carts

Built by the author before the sessions start, and not changed between participants.

| Property | Requirement |
|---|---|
| Blocker | `order.cost.min` in both |
| Gap | equal to within ±15 ₴ between the two carts |
| Branch and channel | identical |
| Line count | identical |
| Products | **no product in common** |
| Delivery slot | booked and valid in both, same day part |

Verify both with `scripts/read_cart_validations.py` before the first session and record the
two readings — a cart that has drifted between sessions invalidates every comparison after
the drift.

**Counterbalance two things, not one:** the order of conditions (A-then-B / B-then-A) and
which cart is used in which condition. With six participants that is three of each
assignment. Counterbalancing only the order would let a difference between the carts
themselves appear as a difference between the conditions.

## 3. Session logistics

Sessions run **strictly sequentially** on the **author's** account. §12.2 forbids two
simultaneous write clients on one cart, so an overlap is not untidy but unsafe — the second
session would be writing to a cart the first is mid-way through.

Between participants the author restores the cart to its starting state and confirms the
restoration with a read. Budget roughly 25 minutes per participant: 5 setup, 2 × 4 task,
~10 questions and reset.

Recruit before the session day, not on it; participants must not have seen the prototype.

## 4. The task, spoken the same way every time

Read verbatim. Do not paraphrase, do not hint, and do not answer "am I doing this right"
during the task — say "do what seems right to you" and note that the question was asked.

> «Уявіть, що ви зібрали кошик і хочете оформити доставку, але замовлення не проходить.
> Ваше завдання — довести кошик до стану, у якому його можна оформити. Робіть так, як
> робили б удома. Я не підказуватиму, і це нормально — я дивлюсь на застосунок, а не на
> вас. Якщо вирішите, що далі не варто, просто скажіть.»

The last sentence matters: a participant must be able to abandon without feeling they
failed, or the completion count measures politeness.

Start the timer when they first touch the screen; stop it at a cart the system accepts, or
at 4 minutes, or when they abandon.

## 5. What is recorded

Per participant, per condition:

| Field | Notes |
|---|---|
| `condition` | A (app) or B (agent) |
| `cart_id` | which of the two carts |
| `order` | first or second in this session |
| `completed` | reached a checkoutable cart within the limit |
| `seconds` | elapsed; **mark censored** when not completed |
| `actions` | taps/clicks to completion |
| `asked_for_help` | whether they asked the moderator anything |
| `blocker_restatement` | verbatim answer to "чому кошик не проходив?" |
| `consent_understanding` | **condition B only**, verbatim answer to "на що саме ви щойно погодились?" |
| `stuck_points` | where they hesitated, in the moderator's words |
| `ratings` | зрозумілість / контроль / довіра, 1–5, asked after both conditions |

`consent_understanding` is the single most valuable field here. Ask it **immediately after
they approve**, before the receipt appears — after the result is visible the answer is
reconstructed rather than recalled.

## 6. Analysis, fixed before any data exists

1. **Completion**: report counts, `x of n`, per condition. Never a percentage at this n.
2. **Paired differences**: for participants who completed **both** conditions, report each
   individual difference in time and actions, and the number of such pairs. No mean, no
   test, no claim of time saved.
3. **Censoring**: an unfinished task keeps its participant in the completion count with the
   time marked censored, never dropped and never counted as a success time.
4. **Blocker restatement**: coded by whether the participant named the actual constraint,
   named something else, or could not say. Two coders would be better; one coder is what
   exists, and that is stated.
5. **Consent understanding**: reported verbatim, not scored. Six quotes are worth more here
   than a number out of five.
6. **Ratings**: report the distribution, not the mean of a 1–5 scale at n = 6.

If n < 5 materialises, §14's own fallback applies: report the honest n. §13.1's rule holds
throughout — `n == 0` is N/A, never 0%.

## 7. What will be written up

Per §14's pass criterion — «n і coverage явні; сценарій відео написаний» — the deliverable
is an honest n with explicit coverage, plus the §15 video script fed by whatever the
sessions actually produced. A significant result is not required and will not be
manufactured.
