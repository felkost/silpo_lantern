# Decision log

Numbered, append-and-amend. A correction gets its own new number and points at the entry
it replaces; the superseded entry gets a dated amendment in place. Never silently rewrite
an entry to make the record look tidy.

---

**D1** (2026-09-05, Stage 0 kickoff) — Repository name stays `silpo_lantern`
(underscore), not `silpo-lantern` (hyphen) as plan §1.6 prescribes.

**Why:** the GitHub repository already exists as `silpo_lantern`; renaming costs a
redirect and touches no code, but the user's explicit choice at kickoff was to keep it.

**Consequence:** §1.6's naming table is followed for everything *inside* the
repository — Python package `lantern/`, Docker services `lantern-api`/`lantern-web` —
only the repository name itself diverges from the plan text.

---

**D2** (2026-09-05, Stage 0 kickoff) — `.claude/` (12 skills, 5 agents, 4 commands) is
listed in `.gitignore` and stays local-only; it is not committed to the public
repository.

**Why:** the repository is public. The skill/agent toolkit is the user's private
portable instrumentation, not project deliverable content, and publishing it would leak
several hundred KB of unrelated instructions into a hackathon submission repo.

**Consequence:** a fresh session on a different machine will not have these skills
available. `handoff.md` names this explicitly so a resuming session does not assume the
toolkit travels with the repository.

---

**D3** (2026-09-05, Stage 0 kickoff) — The kickoff scaffold (this stage) is done before
G0 evidence-lab work, not folded into G1 as the plan's calendar might suggest.

**Why:** the scaffold (directory tree, `CLAUDE.md`, gate, branch protection) needs no MCP
access, no OAuth credentials, and no G0 findings. Building it now frees 06.09 entirely
for G1+G2, the most schedule-constrained day in the rebased calendar (plan §14, V44-01).

**Consequence:** Stage 0 and G0 run as two separate, independently closeable stages, both
inside the 05.09-evening window the plan allocates to G0 alone.

---

**D4** (2026-09-05, Stage 0 kickoff) — `src/lantern/config.py` is added to the directory
tree beyond what plan §21.3 lists verbatim.

**Why:** §21.3 lists packages (`graph, domain, mcp, safety, memory, prompts, policies,
observability`) but no settings module, and the kernel layer (plan §21.3's own layering
table, reused from the layering-test pattern) needs one file with zero project-local
imports to anchor the dependency direction. Kept a module the brief did not name because
its absence is a hole under the brief's own architecture, not a scope expansion.

**Consequence:** `CLAUDE.md`'s layer table lists this file explicitly as `kernel`.

---

**D5** (2026-09-05, Stage 0 kickoff) — `docs/task-lantern-plan-v4-4.md` (the verbatim
brief) stays in Ukrainian, the source language, rather than being translated to English
per the project's general documentation-language policy.

**Why:** it is a verbatim quote of the assignment brief. A translated quote is no longer
a quote — the acceptance criterion for the whole project must stay traceable to the
literal source text a reader (or an auditor) can diff against the original `.docx`.

**Consequence:** this is the one tracked document in the repository that is not English;
`CLAUDE.md`'s language-policy section names it as the deliberate exception.

---

**D6** (2026-09-05, Stage 0 kickoff, superseding plan §5.3's scope boundary for one item)
— The read-only delivery-channel comparison from `docs/plan-amendments.md` amendment A7
is added to the disclosure layer; the §5.2 stretch blockers
(`product.offer.stock.max`, `product.offer.not_found`, `timeslot.not_available`) are
dropped to pay for it under plan rule §5.3 ("adding anything new after G0 requires
dropping something of equal size").

**Why:** A7 is backed by three cross-checked live runs already in hand
(`mcp-field-capability-report.md` §1c, §10.5, §11.5) and is pure read-only arithmetic —
no new DR, no new GD case, no write-path risk. The stretch blockers each still required
their own unproven G0 evidence lab result to even qualify for MVP (plan §5.2: "лише
після відповідного G0-доказу"), so dropping them trades unproven scope for evidence
already on disk.

**Consequence:** G3's domain core spec includes the channel-comparison calculation; G4's
planner does not need to plan stretch-blocker remediation actions. See A7 for the full
argument and its one open caveat (channel switch can drop cart items —
`product.offer.not_found`).

---

**D7** (2026-09-05, Stage 0 kickoff) — Corrections found against field evidence
(`docs/plan-amendments.md`, A1–A8) are recorded as a separate tracked file; the source
`Lantern_Plan_v4_4.docx` is never edited.

**Why:** the plan is explicit in §21 that "FINAL means: plan the stages next, do not
re-litigate the product." Editing the FINAL baseline document would blur which version
was actually reviewed and approved; a dated amendments file keeps the correction visible
next to the original claim rather than silently replacing it.

**Consequence:** any future reader must read `docs/task-lantern-plan-v4-4.md` together
with `docs/plan-amendments.md` — `CLAUDE.md`'s session protocol names both in the fixed
read order.
