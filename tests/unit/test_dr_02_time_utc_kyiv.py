"""DR-02 (plan section 10): time is normalized to UTC internally, displayed
via ZoneInfo("Europe/Kyiv"). Declared failing per plan section 21.3 —
implemented at G3.

Evidence: `[I5]` section 8.3 — a cart's `timeslot.start` of
"2026-08-13T06:30:00+00:00" is 09:30 in Kyiv (summer, UTC+3). A conversion
error gives the worst possible direction: the agent would treat an already
expired slot as still live.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.xfail(strict=True, reason="Time normalizer not implemented until G3")
def test_utc_timeslot_displays_correctly_in_kyiv_time():
    from src.lantern.domain.normalizer import to_kyiv_display  # noqa: F401

    utc_start = datetime.fromisoformat("2026-08-13T06:30:00+00:00")
    displayed = to_kyiv_display(utc_start)

    assert displayed.tzinfo is not None
    assert displayed.astimezone(ZoneInfo("Europe/Kyiv")).hour == 9
    assert displayed.astimezone(ZoneInfo("Europe/Kyiv")).minute == 30
