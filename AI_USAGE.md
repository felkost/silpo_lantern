# AI usage disclosure

This project was built with Claude Code (Anthropic) as a pair-programming assistant
throughout Stage 0 (kickoff) and all subsequent stages. This file states the general
policy; per-stage specifics (what was AI-drafted vs. author-reviewed, what was
independently verified) are recorded in each stage's report under
`docs/reports/G{n}/index.html`, not here and not in commit trailers — see
`CONTRIBUTING.md`'s AI-disclosure policy for why.

## What the assistant did

- Drafted the repository scaffold, `CLAUDE.md`, and all Stage 0 documentation files
  under explicit human direction and review.
- Read the project brief (`Lantern_Plan_v4_4.docx`) and cross-checked it against
  supplementary field-evidence documents supplied by the author, producing
  `docs/plan-amendments.md`.
- Wrote the layering test (adapted from a donor project the author owns) and the five
  declared-failing domain-rule tests.
- Every git-history-writing action (commit, push, PR creation, branch merge) was
  performed by the human author, never by the assistant — see `CLAUDE.md` §6.

## What the human author did

- Set the plan, made every product and scope decision recorded in `docs/decisions.md`.
- Supplied and owns the field-evidence documents and the donor repository
  (`BACKGROUND_MATERIALS.md`).
- Reviewed and approved every standing document (this file included) before it was
  committed.
- Ran every git command; owns the GitHub repository and its branch-protection rules.
