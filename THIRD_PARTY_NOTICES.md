# Third-party notices

## Runtime dependencies

Pinned versions and licenses are declared in `requirements.txt` /
`requirements-dev.txt`. Notable dependencies: FastAPI (MIT), Pydantic (MIT), the
official `mcp` Python SDK (MIT), LangGraph / `langgraph-checkpoint-postgres` (MIT),
LangSmith SDK (MIT), psycopg (LGPL-3.0), SQLAlchemy (MIT), DeepEval (Apache-2.0).
A full license audit runs at G1 once the environment is actually installed; this section
is a placeholder pending that audit — `«…»` where a license has not yet been confirmed
against the installed package's own metadata.

## External services

- **Silpo MCP** (`mcp.silpo.ua`) — official Model Context Protocol server operated by
  Silpo, used under the Silpo AI Factory hackathon's stated terms.
- **OpenRouter** — LLM gateway; models and prices used are recorded, dated, in
  `docs/model-prices-2026-09-05.md`.
- **Neon** — managed Postgres, free tier.
- **LangSmith** (Developer plan, free tier) — trace observability.

## Reused code

See `BACKGROUND_MATERIALS.md` for the full file-by-file list of code reused from the
`MA_systems_SupportFlow` donor project, its owner, and license status.
