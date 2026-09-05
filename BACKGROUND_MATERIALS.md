# Background materials

## Donor project: MA_systems_SupportFlow

- **Owner:** felkost (same author as this project)
- **License:** MIT (both repositories — no license conflict)
- **Location:** `F:\Data\r_d_Multy_Agent Systems\SupportFlow` (local; not a public URL)

Reused code, by file (plan §7.2's REUSE / REPLACE / REMOVE / DEFER breakdown, made
concrete):

| Donor file | Reused as | What was taken |
|---|---|---|
| `tests/test_layering.py` | `tests/unit/test_layering.py` | The AST import-walk pattern (`LAYER_OF` + `ALLOWED` maps, one negative rule beyond plain cross-layer checks). Layer names and the write-allowlist rule are Lantern's own. |
| `src/infrastructure/silpo_mcp_auth.py` | `src/lantern/mcp/auth.py` (G1) | `DiskTokenStorage`, verified against installed `mcp==1.29.0` by direct source inspection; the manual-login contract (`SilpoMcpAuthRequiredError`). |
| `src/infrastructure/silpo_mcp.py` | `src/lantern/mcp/client.py` (G1) | Working Silpo MCP client. **Strengthened per plan §9.1**: dynamic `tools/list` registry, TTL, typed error mapping — the donor version does not have these. |
| `tests/infrastructure/test_silpo_mcp.py` | `tests/contract/` (G1) | Contract-test pattern against recorded MCP responses. |
| `src/kernel/{settings,constants}.py` | `src/lantern/config.py` (G1) | `PROJECT_ROOT` resolution pattern, settings-module shape. |
| `src/interfaces/api.py`, `frontend/` | `apps/api`, `apps/web` (G1) | FastAPI + React/Vite skeleton. |
| `src/infrastructure/observability.py` | `src/lantern/observability/` (G1–G2) | Tracing instrumentation shape — **REPLACE**: Langfuse swapped for LangSmith (plan §7.2, native LangGraph integration). |
| `tests/evaluation/{harness,metrics}.py` | `tests/evals/` (G8+G9) | Evaluation harness skeleton. |
| `config/models.yaml` | `config/models.yaml` (G4) | Model-configuration file pattern. |

**REMOVE** (plan §7.2 — not reused, deliberately): `supervisor.py`, `router_agent.py`,
`a2a_transport.py`, `acp.py`, `docs_agent.py`, `web_search_agent.py`, `*_a2a_server.py`,
`web_search*.py`, `retriever.py`, `telegram_client.py`. Lantern is a single-agent,
deterministic-workflow system (plan §7.1) — no multi-agent orchestration, no A2A
transport, no web search.

**DEFER:** any BM25/vector retrieval component — plan §7.2 keeps this deferred until a
proven need exists (post-G7 `pgvector` option, plan §16), same as the donor.

## Field-evidence materials (`[I1]`–`[I8]` per plan §22.2)

Supplied locally at Stage 0 kickoff (2026-09-05); paths are local to the author's machine.

| Ref | File | Local path | Used for |
|---|---|---|---|
| `[I1]` | `Discord.txt` | `F:\Data\Silpo\Discord.txt` | Organizer Q&A; source of amendments A1, A3–A6 |
| `[I2]` | `Silpo_scenario_lab4.ipynb` | `F:\Data\Silpo\Silpo_scenario_lab4.ipynb` | Donor cells for `notebooks/evidence_lab.ipynb` (OAuth/PKCE flow, snapshot, write/read-back) |
| `[I5]` | `mcp-field-capability-report.md` | `F:\Data\Silpo\mcp-field-capability-report.md` | Primary evidence source for amendments A2, A7; DR-01/02/03/08/12 test fixtures |
| `[I6]` | `mcp-reference-v2.md` | `F:\Data\Silpo\mcp-reference-v2.md` | Validation-code registry (amendment A8), cart arithmetic rules |

`[I3]`, `[I4]`, `[I7]`, `[I8]` (earlier plan revisions and mentor-feedback analysis,
per plan §22.2) were **not** supplied at kickoff — `«…»` where the plan cites them
directly; they are historical context for how v4.4 was reached, not inputs this scaffold
depended on.
