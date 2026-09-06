"""Request/response Pydantic models for the session/consent routes
(plan section 1.5). Kept separate from `main.py` so the route module
stays focused on wiring, not shape declarations.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CreateSessionResponse(BaseModel):
    session_id: str
    trace_id: str
    status: str
    error: Optional[str] = None
    primary_code: Optional[str] = None
    gap: Optional[str] = None
    candidates: List[Dict[str, Any]] = []


class ConsentRequest(BaseModel):
    """D-G5-18/T18: the guest picks an `action_id` only. `args_hash` and
    `state_hash` are never accepted from the client -- the server
    recomputes both from the proposal and cart it already holds, so a
    tampered value on the wire has nothing to overwrite."""

    action_id: str


class ConsentResponse(BaseModel):
    status: str
    reason: Optional[str] = None
    actual_delta: Optional[Decimal] = None
