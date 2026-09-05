# Insights

Append-only. One entry per event, written at the moment of the event. Categories:
`Pattern` (a shape worth repeating), `Mistake` (something that cost time), `Decision`
(a choice made, with its reason — mirrored in `docs/decisions.md` if project-wide),
`Quirk` (a library or platform behaving unexpectedly).

---

**2026-09-05 [Quirk]** — Bash heredocs (`cat > file << 'EOF'`) intermittently fail with
"unexpected EOF while looking for matching ''" on this Git Bash/MSYS shell when the body
contains many Ukrainian-text apostrophes mixed with markdown emphasis across a long
multi-section file; root cause not fully isolated. Switched to the `Write` tool for large
markdown files with mixed English/Ukrainian prose and heavy quoting; kept heredocs for
short, single-purpose files (JSON, `.gitignore`, single-command scripts).

**2026-09-05 [Quirk]** — `deepseek/deepseek-v4-flash` is a live alias on OpenRouter, not
a pinned model id; it currently resolves to `deepseek/deepseek-v4-flash-0731`. Pin the
dated id in `config/models.yaml` at IV-05, not the alias — see
`docs/model-prices-2026-09-05.md`.

**2026-09-05 [Decision]** — Kept the DR-03 epsilon rule even after confirming (amendment
A2) that the anomaly which originally motivated it was a units-confusion bug, not a real
server inconsistency. See `docs/decisions.md` D-none (recorded under amendment A2 in
`docs/plan-amendments.md` since it did not need its own numbered decision — no scope
changed, only a risk severity).
