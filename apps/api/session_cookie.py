"""the session id lives in an `HttpOnly; Secure;
SameSite=Lax` cookie. `HttpOnly` keeps it from page script, `Secure`
keeps it off plain http, `SameSite=Lax` closes cross-site POSTs -- the
ordinary web-session model. Route paths still carry `{session_id}`
for the SPA's own fetches, so every such route checks the path against
the cookie: a leaked id is worthless without the browser that holds it.
"""

from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "lantern_session"


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def cookie_session_id(request: Request) -> str:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="no session cookie")
    return session_id


def require_session_cookie(request: Request, session_id: str) -> None:
    if cookie_session_id(request) != session_id:
        raise HTTPException(status_code=401, detail="session cookie does not match")
