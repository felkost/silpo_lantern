"""the two spend caps. `POST /session` is unauthenticated and
every live graph start bills the author's OpenRouter key, so the service
needs a limit before its URL is shared -- not because anyone can read
another guest's cart (they cannot), but because anyone can spend the
project's money. The ceiling is set from a measured figure: $0.116 for 18
runs (`g9_core_e2e_repeats_20260909T202521Z.json`), about $0.0064 a run.

In-process counters keyed by UTC day, same single-worker assumption
`oauth_pending` already makes.
ponytail: counters reset on every restart (Render's free tier sleeps), so
the daily ceiling is a per-uptime ceiling in practice; move to a Postgres
row if the budget ever needs to survive a restart.
"""

import time
from typing import Callable, Dict

DEFAULT_SESSIONS_PER_IP = 10
DEFAULT_LLM_RUNS_PER_DAY = 40  # ~$0.26 at the measured per-run cost


class SpendCaps:
    def __init__(
        self,
        sessions_per_ip: int = DEFAULT_SESSIONS_PER_IP,
        llm_runs_per_day: int = DEFAULT_LLM_RUNS_PER_DAY,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._sessions_per_ip = sessions_per_ip
        self._llm_runs_per_day = llm_runs_per_day
        self._clock = clock
        self._day = ""
        self._sessions: Dict[str, int] = {}
        self._llm_runs = 0

    def _roll(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        if day != self._day:
            self._day, self._sessions, self._llm_runs = day, {}, 0

    def admit_session(self, ip: str) -> bool:
        self._roll()
        if self._sessions.get(ip, 0) >= self._sessions_per_ip:
            return False
        self._sessions[ip] = self._sessions.get(ip, 0) + 1
        return True

    def admit_llm_run(self) -> bool:
        self._roll()
        if self._llm_runs >= self._llm_runs_per_day:
            return False
        self._llm_runs += 1
        return True
