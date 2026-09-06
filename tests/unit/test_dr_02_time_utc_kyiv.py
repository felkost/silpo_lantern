"""DR-02 (plan section 10): time is normalized to UTC internally, displayed
via ZoneInfo("Europe/Kyiv"). Implemented at G3
(`src/lantern/domain/normalizer.py`).

Evidence: `[I5]` section 8.3 — a cart's `timeslot.start` of
"2026-08-13T06:30:00+00:00" is 09:30 in Kyiv (summer, UTC+3). A conversion
error gives the worst possible direction: the agent would treat an already
expired slot as still live.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.lantern.domain.normalizer import to_kyiv_display


def test_utc_timeslot_displays_correctly_in_kyiv_time():
    utc_start = datetime.fromisoformat("2026-08-13T06:30:00+00:00")
    displayed = to_kyiv_display(utc_start)

    assert displayed.tzinfo is not None
    assert displayed.astimezone(ZoneInfo("Europe/Kyiv")).hour == 9
    assert displayed.astimezone(ZoneInfo("Europe/Kyiv")).minute == 30
