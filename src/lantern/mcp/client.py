"""MCP client: port of the donor project's `silpo_mcp.py`, strengthened with
a dynamic `tools/list` registry (TTL + event-driven invalidation) and typed
error mapping — both measured to have zero donor precedent.

`ToolRegistry` is per-process by design: it has no shared store across
worker processes. A forked worker cannot reliably detect its own siblings,
so this stays a documented constraint checked at code/PR review (the launch
command must not pass a `--workers`/`WEB_CONCURRENCY` value greater than
1), not an enforced runtime check.
"""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set

from mcp import types as mcp_types

from src.lantern.mcp.errors import (
    McpAdapterError,
    McpProtocolError,
    McpResponseTooLargeError,
    McpSchemaError,
    McpToolExecutionError,
)

# JSON-RPC codes that are themselves evidence the cached schema is stale.
_SCHEMA_INVALIDATING_CODES = {
    mcp_types.METHOD_NOT_FOUND,
    mcp_types.INVALID_PARAMS,
}

# The MCP server is this project's own stated untrusted threat model.
# Bounds are a defensive ceiling, not a measured limit — 40 tools is the
# largest response seen so far.
MAX_TOOL_COUNT = 500
MAX_RESPONSE_BYTES = 5_000_000


# A tracked file colocated with this module, not under `config/` (which so
# far only holds operational settings like generator seeds and LLM model
# ids, not a security-relevant allowlist) and not under `tests/` (production
# code must not import from the test tree). Mirrors
# `src/lantern/policies/registry.yaml`'s own placement alongside its
# loader — data a specific package owns lives inside that package, not in a
# shared top-level directory.
_REVIEWED_TOOLS_PATH = Path(__file__).resolve().parent / "reviewed_tools.json"


@lru_cache(maxsize=1)
def load_reviewed_tool_names() -> FrozenSet[str]:
    """The tracked baseline of tool names already reviewed: a new or changed
    tool is quarantined until reviewed, never auto-trusted. Generated from
    the tracked contract fixture — see `reviewed_tools.json`'s own
    `source`/`source_schema_hash` fields for provenance, so a future reader
    can re-derive it rather than trust this docstring.

    Cached for the process's lifetime: this is static release data that
    only changes via a deliberate review producing a new committed file,
    never a mid-process event — re-reading it on every `tools/list` fetch
    would add I/O with no corresponding benefit.
    """
    payload = json.loads(_REVIEWED_TOOLS_PATH.read_text(encoding="utf-8"))
    return frozenset(payload["names"])


def compute_schema_hash(tools_raw: List[Dict[str, Any]]) -> str:
    """sha256 over the canonical JSON of a raw `tools/list` `tools` array —
    matching the hashing already used by the evidence lab
    (`notebooks/evidence_lab.ipynb`, `json.dumps(tools, ensure_ascii=False,
    indent=2)`), so a recorded snapshot's `schema_hash` stays reproducible.
    """
    canonical = json.dumps(tools_raw, ensure_ascii=False, indent=2)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def raise_on_tool_error(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """`CallToolResult.isError` is a field the caller must check — the SDK
    does not raise for it. Never let a caller treat an `isError: true` payload
    as ordinary data.
    """
    if result.isError:
        raise McpToolExecutionError(content=result.content)
    return result


@dataclass(frozen=True)
class CachedTools:
    result: mcp_types.ListToolsResult
    fetched_at: float
    unknown_to_registry: FrozenSet[str]
    # Hashed over the RAW tools array, before any SDK type parsing touches
    # it. A hash taken after parsing into `mcp_types.Tool` and back does not
    # reproduce this value — proven by a failing probe, not assumed
    # (`tests/contract/test_schema_hash_survives_typed_roundtrip.py`): the
    # SDK's `Tool` model adds `_meta`/`icons` fields the wire payload never
    # had, so no `model_dump` option set recovers byte equality with the raw
    # JSON.
    schema_hash: str
    # Unlike `unknown_to_registry` (relative to this process's own fetch
    # history, resets on restart), `quarantined` is checked against the
    # tracked baseline in `reviewed_tools.json`, which survives one. Drift
    # here is not fatal — see `tool_view.py`: a quarantined tool is simply
    # never exposed to the graph, the read path on the reviewed set
    # continues unaffected.
    quarantined: FrozenSet[str]


def _reject_if_oversized(tools_raw: List[Dict[str, Any]]) -> None:
    """Reject before any hashing/diffing work is spent on the response.
    Operates on the raw list so the ceiling is checked before SDK parsing,
    not after — parsing an oversized payload into typed objects first would
    defeat the point of rejecting it early.
    """
    if len(tools_raw) > MAX_TOOL_COUNT:
        raise McpResponseTooLargeError(
            f"tools/list returned {len(tools_raw)} tools, over the "
            f"{MAX_TOOL_COUNT} ceiling"
        )
    size = len(json.dumps(tools_raw, ensure_ascii=False).encode("utf-8"))
    if size > MAX_RESPONSE_BYTES:
        raise McpResponseTooLargeError(
            f"tools/list response is {size} bytes, over the "
            f"{MAX_RESPONSE_BYTES} ceiling"
        )


class ToolRegistry:
    """Caches the last `tools/list` response with a wall-clock TTL — a
    defensive floor under event-driven invalidation, not a replacement for
    it — and flags tool names not seen on any previous fetch (tool-name
    drift only; validation-code drift is a different data path entirely).
    """

    def __init__(
        self,
        fetch: Callable[[], List[Dict[str, Any]]],
        ttl_seconds: float,
        now: Callable[[], float],
    ) -> None:
        self._fetch = fetch
        self._ttl_seconds = ttl_seconds
        self._now = now
        self._cached: Optional[CachedTools] = None
        self._known_names: Set[str] = set()

    def get(self, force_refresh: bool = False) -> CachedTools:
        if not force_refresh and self._cached is not None:
            age = self._now() - self._cached.fetched_at
            if age < self._ttl_seconds:
                return self._cached
        return self._refresh()

    def invalidate(self) -> None:
        self._cached = None

    def observe_error(self, error: McpAdapterError) -> None:
        """Invalidate immediately on evidence the cached schema is stale,
        rather than waiting out the TTL. A `McpSchemaError` (cached
        `inputSchema` rejected a call's arguments) always invalidates; a
        `McpProtocolError` invalidates only for the codes named above — an
        unrelated protocol error is not itself evidence the schema drifted.
        """
        if isinstance(error, McpSchemaError):
            self.invalidate()
        elif (
            isinstance(error, McpProtocolError)
            and error.code in _SCHEMA_INVALIDATING_CODES
        ):
            self.invalidate()

    def _refresh(self) -> CachedTools:
        # Hash and size-check the RAW list first — before any SDK parsing —
        # then derive typed `Tool` objects from that same raw data. One
        # payload, two derived views, in that order.
        tools_raw = self._fetch()
        _reject_if_oversized(tools_raw)
        schema_hash = compute_schema_hash(tools_raw)
        result = mcp_types.ListToolsResult(
            tools=[mcp_types.Tool.model_validate(t) for t in tools_raw]
        )
        names = {t.name for t in result.tools}
        # First fetch ever establishes the baseline — nothing is "new"
        # relative to an empty registry, only relative to a previously
        # observed one.
        new_names = names - self._known_names if self._known_names else set()
        self._known_names |= names
        quarantined = names - load_reviewed_tool_names()
        cached = CachedTools(
            result=result,
            fetched_at=self._now(),
            unknown_to_registry=frozenset(new_names),
            schema_hash=schema_hash,
            quarantined=frozenset(quarantined),
        )
        self._cached = cached
        return cached
