"""MCP client: port of the donor's `silpo_mcp.py` (BACKGROUND_MATERIALS.md),
strengthened per plan section 9.1 with a dynamic `tools/list` registry (TTL +
event-driven invalidation) and typed error mapping — both measured to have
zero donor precedent (docs/g1-g2-stage-spec.md section 2).

`ToolRegistry` is per-process by design (F9, docs/g1-g2-stage-spec.md): it has
no shared store across worker processes this stage. A forked worker cannot
reliably detect its own siblings, so this stays a documented constraint
checked at code/PR review (the launch command must not pass a
`--workers`/`WEB_CONCURRENCY` value greater than 1), not an enforced runtime
check.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set

from mcp import types as mcp_types

from src.lantern.mcp.errors import (
    McpAdapterError,
    McpProtocolError,
    McpResponseTooLargeError,
    McpSchemaError,
    McpToolExecutionError,
)

# F3: JSON-RPC codes that are themselves evidence the cached schema is stale —
# see docs/g1-g2-stage-spec.md section 4 and plan section 9.1's invalidation list.
_SCHEMA_INVALIDATING_CODES = {
    mcp_types.METHOD_NOT_FOUND,
    mcp_types.INVALID_PARAMS,
}

# F11: the MCP server is this project's own stated untrusted threat model
# (CLAUDE.md section 4). Bounds are a defensive ceiling, not a measured
# limit — 40 tools is the largest response seen so far (D8).
MAX_TOOL_COUNT = 500
MAX_RESPONSE_BYTES = 5_000_000


def compute_schema_hash(tools_raw: List[Dict[str, Any]]) -> str:
    """sha256 over the canonical JSON of a raw `tools/list` `tools` array —
    matching the hashing already used by the G0 evidence lab
    (`notebooks/evidence_lab.ipynb`, `json.dumps(tools, ensure_ascii=False,
    indent=2)`), so a recorded snapshot's `schema_hash` stays reproducible.
    """
    canonical = json.dumps(tools_raw, ensure_ascii=False, indent=2)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def raise_on_tool_error(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """F6: `CallToolResult.isError` is a field the caller must check — the SDK
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


def _reject_if_oversized(result: mcp_types.ListToolsResult) -> None:
    """F11: reject before any hashing/diffing work is spent on the response."""
    if len(result.tools) > MAX_TOOL_COUNT:
        raise McpResponseTooLargeError(
            f"tools/list returned {len(result.tools)} tools, over the "
            f"{MAX_TOOL_COUNT} ceiling"
        )
    size = len(result.model_dump_json().encode("utf-8"))
    if size > MAX_RESPONSE_BYTES:
        raise McpResponseTooLargeError(
            f"tools/list response is {size} bytes, over the "
            f"{MAX_RESPONSE_BYTES} ceiling"
        )


class ToolRegistry:
    """Caches the last `tools/list` response with a wall-clock TTL
    (D-G1-08 — a defensive floor under plan section 9.1's event-driven
    invalidation, not a replacement for it), and flags tool names not seen on
    any previous fetch (F4/D8 — tool-name drift only; validation-code drift
    is a different data path entirely and is G3's job, F4b).
    """

    def __init__(
        self,
        fetch: Callable[[], mcp_types.ListToolsResult],
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
        """F3: invalidate immediately on evidence the cached schema is
        stale, rather than waiting out the TTL. A `McpSchemaError` (cached
        `inputSchema` rejected a call's arguments) always invalidates; a
        `McpProtocolError` invalidates only for the codes named in plan
        section 9.1's own list — an unrelated protocol error is not itself
        evidence the schema drifted.
        """
        if isinstance(error, McpSchemaError):
            self.invalidate()
        elif (
            isinstance(error, McpProtocolError)
            and error.code in _SCHEMA_INVALIDATING_CODES
        ):
            self.invalidate()

    def _refresh(self) -> CachedTools:
        result = self._fetch()
        _reject_if_oversized(result)
        names = {t.name for t in result.tools}
        # First fetch ever establishes the baseline — nothing is "new"
        # relative to an empty registry, only relative to a previously
        # observed one.
        new_names = names - self._known_names if self._known_names else set()
        self._known_names |= names
        cached = CachedTools(
            result=result,
            fetched_at=self._now(),
            unknown_to_registry=frozenset(new_names),
        )
        self._cached = cached
        return cached
