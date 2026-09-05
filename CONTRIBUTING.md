# Contributing

## Gate chain

```bash
make gate
```

runs `black --check . tests/*.py && flake8 && mypy src && pytest -q` as one chain. It
must pass before any PR is opened. It never calls a live LLM or a live MCP endpoint.

## Branches and commits

- One branch per stage: `stage/<name>` off `main`. `main` is protected — direct pushes
  are rejected by a GitHub ruleset (see `.github/rulesets/main.json`); every change
  lands through a pull request.
- Commit messages: imperative mood, English, no trailer of any kind. In particular:
  **no `Co-Authored-By` trailer, no AI-disclosure trailer.** A trailer becomes a
  permanent contributor-graph entry a history rewrite cannot reliably remove.
- The assistant never runs `git commit`, `git push`, or `gh pr create`. Commands are
  printed, one per line, in execution order; the author runs them.

## Size bands

- A Python module: split before ~400 lines of actual code (see `CLAUDE.md` §5 for the
  measured reason this project uses that number).
- A stage: one branch, one PR, one independently verifiable increment — see
  `docs/decisions.md` and the stage table in `docs/task-lantern-plan-v4-4.md` §14.

## Language policy

Chat: Ukrainian. Code, comments, identifiers, tracked documents, commit messages, PR
bodies, diagrams: English. Exceptions: `docs/task-lantern-plan-v4-4.md` (verbatim brief)
and `apps/web` UI copy / pitch materials (Ukrainian by plan §1.6). See `CLAUDE.md` §8.

## AI-disclosure policy

Disclosure of AI-assisted work lives in the **stage report**
(`docs/reports/G{n}/index.html`), not in any commit trailer. This keeps the git history
clean for a public hackathon submission while keeping the disclosure honest and visible
in the one place a reader actually looks for it.
