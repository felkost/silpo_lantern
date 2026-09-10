"""The sync repository pool must survive a connection the SERVER dropped
while the client still thinks it is open -- Neon's idle-suspend, or a
Render service waking after sleep. Seen live at G10 delivery C: the first
`/events` after ~20 idle minutes answered 500 with `SSL connection has
been closed unexpectedly`. The checkpointer's own recovery test closes the
socket client-side, which the pool detects by `conn.closed`; this one kills
the backend server-side, which nothing detects until the connection is
used -- unless the pool checks it on checkout.
"""

import os
import socket

import pytest

from src.lantern.config import strip_sqlalchemy_dialect
from src.lantern.memory.repository import get_session, open_repository_pool

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


def test_a_dropped_socket_is_replaced_not_reused() -> None:
    """`pg_terminate_backend` cannot be used here: Neon's pooler shares one
    backend between connections, so the killer terminates itself. Shutting
    the socket underneath psycopg is the same event from the client's
    side -- the object still reports `closed == False`."""
    dsn = strip_sqlalchemy_dialect(os.environ["DATABASE_URL"])
    with open_repository_pool(dsn) as pool:
        victim = pool.getconn()
        # Wrap the live handle, shut it, detach so the wrapper does not
        # close it too (psycopg keeps the handle; on Windows it is not an fd).
        wrapper = socket.socket(fileno=victim.fileno())
        wrapper.shutdown(socket.SHUT_RDWR)
        wrapper.detach()
        assert not victim.closed  # looks alive
        pool.putconn(victim)

        # Must not raise: the pool must hand out a live connection.
        assert get_session(pool, "00000000-0000-0000-0000-000000000000") is None
