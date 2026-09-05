# Handoff

**Status as of 2026-09-05, Stage 0 (kickoff), not yet committed.** A fresh session's
first move is `git log --oneline -5` and `git status --short --branch`, not trusting
this file's snapshot — the log below is what those commands showed at the moment this
was written, on branch `stage/s0-kickoff`, 67 new files staged, HEAD still at
`744b066` (the origin's initial commit, `LICENSE` only).

## What is done

| Item | State |
|---|---|
| Directory tree (plan §21.3 + kernel config, decision D4) | done |
| `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `insights.md` | done |
| `BACKGROUND_MATERIALS.md`, `AI_USAGE.md`, `THIRD_PARTY_NOTICES.md` | done |
| `docs/task-lantern-plan-v4-4.md` (verbatim brief) | done |
| `docs/plan-amendments.md` (A1–A8, checked against `[I1][I5][I6]` and Discord) | done |
| `docs/decisions.md` (D1–D7) | done |
| `docs/requirements-checklist.md` | done |
| `docs/model-prices-2026-09-05.md` (live OpenRouter catalogue, all 7 ids confirmed) | done |
| `docs/uml/*.mmd` + `svg/*.svg` (extracted from `lantern_uml_seed_v4.4.zip`) | done |
| `.gitignore`, `.env.example`, `Makefile`, `docker-compose.yml`, `pyproject.toml`, `.flake8` | done |
| `requirements.txt` / `requirements-dev.txt` (pinned) | done |
| `.github/rulesets/main.json` — **applied live** (ruleset id 22351059, `bypass_actors: []`) | done, confirmed on GitHub |
| `.github/workflows/ci.yml` (no required status check yet — by design, see plan step 2) | done |
| `tests/unit/test_layering.py` (3 tests, adapted from SupportFlow donor) | done, passing |
| 5 declared-failing DR tests (DR-01/02/03/08/12, `xfail(strict=True)`) | done, 7 xfailed as expected |
| `scripts/secret_scan.py`, `scripts/render_report.py` | done, both verified working |
| `docs/reports/S0/index.html`, `docs/reports/index.html` | done, rendered, opens with no network |
| `notebooks/evidence_lab.ipynb` (23 cells, adapted from `Silpo_scenario_lab4.ipynb`) | done, valid JSON, all code cells syntax-checked |
| `datasets/fixtures/manifest.json`, `envelope.schema.json` (empty skeletons) | done |

## What is merged

Nothing yet. `main` has only the original `LICENSE` commit (`744b066`). All Stage 0
work is staged on `stage/s0-kickoff`, uncommitted.

## What is uncommitted

Everything listed above as "done" — 67 files, `git add -A` already run, `git status
--short --branch` shows them all as `A` (staged, not committed). **The author commits
and pushes** — see "Next steps" below.

## What the last stage built, and what broke

This is the first stage; nothing broke. One tooling note for `insights.md`: Bash
heredocs (`cat > file << 'EOF'`) intermittently failed with "unexpected EOF" on this
shell for large files mixing Ukrainian apostrophes and markdown emphasis — worked
around by using the `Write` tool for those files instead of heredocs.

## Verification already run this session

```
make gate            -> 3 passed, 7 xfailed, exit 0
make secret-scan      -> 0 findings
make report GATE=S0   -> docs/reports/S0/index.html (opened in browser, confirmed rendering)
git push origin main  -> NOT YET TESTED (requires the author's push; ruleset is live)
```

## Open items / diagnosed blockers

- **G0 itself has not run.** `notebooks/evidence_lab.ipynb` needs the author's own MCP
  OAuth login (phone+OTP in browser) — cannot be run by the assistant. This is the
  next session's first task after this scaffold merges.
- **`docs/reports/S0/index.html` and `notebooks/evidence_lab.ipynb` have CRLF line
  endings** on this Windows checkout — git warns it will normalize to LF on next touch.
  Harmless, noted for awareness only.
- **`required_status_checks` on the branch ruleset is deliberately not yet enabled** —
  add it after this PR's CI run is green once, so the required check actually exists
  before it is required (plan Stage 0, step 2).

## Money spent this session

$0. The one live network call this session (OpenRouter model catalogue via WebFetch)
does not draw against the project's $20 LLM budget — it queried public pricing
metadata, not a chat completion.

## Next steps — commands for you to run, one per line

```bash
git add -A
```

```bash
git commit -m "Stage 0: kickoff scaffold, no application code yet"
```

```bash
git push -u origin stage/s0-kickoff
```

```bash
gh pr create --title "Stage 0: kickoff scaffold" --body "Repository scaffold per docs/decisions.md and docs/plan-amendments.md. No application code — gate is green on layering + 5 declared-failing DR tests. See docs/reports/S0/index.html."
```

After CI runs green on the PR once:

```bash
gh api --method PUT repos/felkost/silpo_lantern/rulesets/22351059 --input .github/rulesets/main-with-checks.json
```

(that file does not exist yet — add the `required_status_checks` rule to a copy of
`.github/rulesets/main.json` naming the `gate` job before running this, or ask the
assistant to prepare it once the PR's check name is confirmed on GitHub)

```bash
gh pr merge --squash
```

Then tell the assistant the PR is merged — it will sync `main` and delete the branch
locally and on GitHub, per your standing authorization.

## Resume prompt (paste this to a fresh session)

> Continue the Lantern project. Read `handoff.md`, then `git log --oneline -5` and
> `git status --short --branch` to check its snapshot, then `CLAUDE.md`, then
> `docs/requirements-checklist.md`, then `docs/plan-amendments.md`. Stage 0 (kickoff
> scaffold) is built and staged/committed as of 2026-09-05 — check whether the PR has
> merged. If it has, the next stage is **G0** (evidence lab): open
> `notebooks/evidence_lab.ipynb` and run it cell by cell with your own MCP login; after
> G0's evidence lands in `docs/evidence/`, the next stage is **G1+G2** (FastAPI/React
> scaffold, Neon, MCP registry — see the stage table in the approved plan file).
