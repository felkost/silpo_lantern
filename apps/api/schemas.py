"""Request/response Pydantic models for the session/consent routes
. Kept separate from `main.py` so the route module
stays focused on wiring, not shape declarations.
"""

from pydantic import BaseModel


class CreateSessionResponse(BaseModel):
    """`POST /session` only creates the session row and returns its id --
    the graph does not run yet (real live push). A new session has
    no guest token yet, so `authorized` is False and `auth_url` is where
    the client sends the guest to log in (phone + OTP at Silpo's own
    page); `GET /session/{id}/events` comes after that."""

    session_id: str
    status: str = "created"
    authorized: bool = False
    auth_url: str = ""


class ConsentRequest(BaseModel):
    """the guest picks an `action_id` only. `args_hash` and
    `state_hash` are never accepted from the client -- the server
    recomputes both from the proposal and cart it already holds, so a
    tampered value on the wire has nothing to overwrite."""

    action_id: str


class ConsentAckResponse(BaseModel):
    """Acknowledges that consent was recorded and the graph's checkpoint
    was updated to resume into the Write Guard -- NOT the write's own
    outcome. The guest's client reconnects to `GET /session/{id}/events`
    to see `receipt`/`error` for the write itself, the same way it saw
    `diagnosis`/`options`/`consent_required` for the read pipeline."""

    status: str = "consent_recorded"
    action_id: str
    # the binding as recorded, so the console can show the
    # hash the guard will compare against the candidate's. No `cart_id`,
    # ever.
    args_hash: str = ""
    state_hash: str = ""
    expires_at: str = ""
