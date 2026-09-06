"""On Windows, asyncio's default `ProactorEventLoop` cannot run psycopg's
async mode at all (measured: `psycopg.InterfaceError` on the very first
`AsyncConnection.connect`, not a corner case). `WindowsSelectorEventLoopPolicy`
is psycopg's own documented workaround. Set once, at test-session start, so
every async test that touches the checkpointer or a raw psycopg connection
works identically on this development machine and in CI (Linux's default
loop is unaffected by this policy).
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
