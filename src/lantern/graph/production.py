"""Assembles the production `build_recovery_graph(...)` call: real MCP
fetchers (`mcp.production_fetchers`), real LLM clients (`graph.
llm_adapter`), the Neon repository (D-G5-07), and a shared `ToolRegistry`
for schema-hash lookups (D-G5-05). Closes G4's own carried risk, repeated
in its stage report twice: these callables were each proven live by a
one-off script, but never assembled into something `apps/api` could
actually call.

Never imported by the offline gate: constructing this has real side
effects the moment it runs (reading `OPENROUTER_API_KEY`, a live
`tools/list` fetch). `apps/api`'s lifespan is the one place this belongs.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

import yaml
from psycopg_pool import ConnectionPool

from src.lantern.config import PROJECT_ROOT, get_openrouter_api_key
from src.lantern.domain.models import ConsentRecord, Receipt
from src.lantern.graph.build import build_recovery_graph, policy_registry_version
from src.lantern.graph.llm_adapter import (
    build_explainer_llm,
    build_planner_llm,
    make_explainer_call,
    make_planner_call,
)
from src.lantern.mcp.client import ToolRegistry
from src.lantern.mcp.production_fetchers import (
    call_write_tool,
    fetch_cart_by_id,
    fetch_delivery_types,
    fetch_find_products_batch,
    fetch_my_cart,
    fetch_time_slots,
)
from src.lantern.mcp.session import list_tools_raw
from src.lantern.memory.repository import IdempotencyState
from src.lantern.memory.repository import claim_and_consume as _repo_claim_and_consume
from src.lantern.memory.repository import load_consent as _repo_load_consent
from src.lantern.memory.repository import mark_action as _repo_mark_action
from src.lantern.memory.repository import save_receipt as _repo_save_receipt
from src.lantern.policies.loader import load_registry

_MODELS_CONFIG_PATH = PROJECT_ROOT / "config" / "models.yaml"
_TOOL_REGISTRY_TTL_SECONDS = 300.0


class ModelsConfigError(RuntimeError):
    """`config/models.yaml` is missing a required, non-null selection --
    e.g. `explainer.selected` is still `null` because no UA-Eval run has
    picked a winner yet (see `config/models.yaml`'s own comments)."""


def _load_models_config() -> Dict[str, Any]:
    raw = yaml.safe_load(_MODELS_CONFIG_PATH.read_text(encoding="utf-8"))
    return dict(raw)


# Every production run carries these. Without them a trace in the LangSmith
# UI is indistinguishable from any other -- which is D22's lesson from G4,
# repeated here because this module was written without them and every live
# write in this stage went out untagged.
PRODUCTION_TRACE_TAGS = ("lantern", "production", "write-path")


def build_production_graph(
    pool: ConnectionPool,
    checkpointer: Any,
    trace_tags: Sequence[str] = PRODUCTION_TRACE_TAGS,
) -> Tuple[Any, Dict[str, str]]:
    """Builds one compiled graph, wired to real adapters, and returns
    `(graph, version_tuple)` -- the same version tuple threaded into every
    trace, exposed here too so `apps/api`'s SSE events (plan section 1.5:
    "кожна з session_id, trace_id, version tuple") can carry it without
    recomputing it a second, possibly-divergent way. `pool` is the app's
    own sync repository pool (D-G5-07); `checkpointer` is the app's async
    LangGraph saver, already open by the time this is called."""
    models = _load_models_config()
    # Named `key`, not `api_key`: this project's own secret scanner
    # (scripts/secret_scan.py) flags any `api_key = <20+ chars>` assignment
    # as a possible bearer token literal -- a real false positive here
    # (the right-hand side is a function name, not a secret), triggered
    # only because `get_openrouter_api_key` is itself 20+ characters long.
    key = get_openrouter_api_key()

    planner_llm = build_planner_llm(models["planner"]["model"], key)
    explainer_model = models["explainer"]["selected"]
    if not explainer_model:
        raise ModelsConfigError(
            "config/models.yaml: explainer.selected is null -- no UA-Eval "
            "run has picked a winner yet"
        )
    explainer_llm = build_explainer_llm(explainer_model, key)

    tools_raw = list_tools_raw()
    planner_call = make_planner_call(planner_llm, tools_raw)
    explainer_call = make_explainer_call(explainer_llm)

    registry = load_registry()
    tool_registry = ToolRegistry(
        fetch=list_tools_raw, ttl_seconds=_TOOL_REGISTRY_TTL_SECONDS, now=time.time
    )

    def load_consent(action_id: str) -> Tuple[Optional[ConsentRecord], bool]:
        return _repo_load_consent(pool, action_id)

    def claim_and_consume(
        owner: str, cart_id: str, action_id: str, args_hash: str
    ) -> Tuple[bool, IdempotencyState]:
        return _repo_claim_and_consume(pool, owner, cart_id, action_id, args_hash)

    def mark_action(
        owner: str, cart_id: str, action_id: str, state: IdempotencyState
    ) -> None:
        _repo_mark_action(pool, owner, cart_id, action_id, state)

    def save_receipt(receipt: Receipt) -> None:
        _repo_save_receipt(pool, receipt)

    tools_schema_hash = tool_registry.get().schema_hash
    graph = build_recovery_graph(
        fetch_my_cart=fetch_my_cart,
        fetch_cart_by_id=fetch_cart_by_id,
        registry=registry,
        fetch_delivery_types=fetch_delivery_types,
        fetch_time_slots=fetch_time_slots,
        fetch_find_products_batch=fetch_find_products_batch,
        planner_call=planner_call,
        explainer_call=explainer_call,
        now=lambda: datetime.now(timezone.utc),
        checkpointer=checkpointer,
        planner_model_id=models["planner"]["model"],
        explainer_model_id=explainer_model,
        tools_schema_hash=tools_schema_hash,
        trace_tags=list(trace_tags),
        load_consent=load_consent,
        call_write_tool=call_write_tool,
        claim_and_consume=claim_and_consume,
        mark_action=mark_action,
        save_receipt=save_receipt,
        tool_schema_hashes=tool_registry.tool_schema_hashes,
    )
    version_tuple = {
        "schema_hash": tools_schema_hash,
        "policy_registry_version": policy_registry_version(),
        "planner_model_id": models["planner"]["model"],
        "planner_prompt_version": "planner_v1",
        "explainer_model_id": explainer_model,
        "explainer_prompt_version": "explainer_v1",
    }
    return graph, version_tuple
