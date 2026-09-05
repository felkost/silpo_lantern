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

- A Python module: split before roughly 400 lines of actual code — the donor project's
  own MCP client file had already crossed its own ceiling before tracing
  instrumentation was added to it, which is exactly why the OAuth logic lives in its
  own file in this project.
- A stage: one branch, one PR, one independently verifiable increment.

## Language policy

Chat: Ukrainian. Code, comments, identifiers, tracked documents, commit messages, PR
bodies, diagrams: English. The project's internal brief and pitch materials are kept in
Ukrainian by design; those are maintained locally, not part of this repository.

## AI-disclosure policy

Disclosure of AI-assisted work is maintained internally, per stage, and is not part of
the public repository.
