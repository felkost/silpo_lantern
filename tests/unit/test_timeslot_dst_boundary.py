"""G9 (GD-10): the DST-boundary property of the
`timeslot_spans_dst_transition` fixture, pinned at the normalizer level.

GD-10's golden case asserts the end-to-end graph behaviour (the timeslot
blocker is surfaced as known, nothing crashes). What a golden case cannot
express through the runner's outcome keys is the conversion property that
makes this fixture worth having at all: both endpoints of a genuinely
one-hour window read 03:30 in Kyiv, because the clock goes back between
them. A naive wall-clock comparison sees start == end and concludes the
window is empty -- or, worse in the direction that matters, treats an
expired slot as still live (DR-02's own stated failure direction).

One source of truth for the data (the tracked fixture), two levels of
assertion (here and in the golden case).
"""

import json
from zoneinfo import ZoneInfo

from src.lantern.config import PROJECT_ROOT
from src.lantern.domain.normalizer import normalize_cart

FIXTURE_PATH = (
    PROJECT_ROOT
    / "datasets"
    / "fixtures"
    / "mutated"
    / "timeslot_spans_dst_transition.json"
)
KYIV = ZoneInfo("Europe/Kyiv")


def _cart():
    envelope = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return normalize_cart(envelope["payload"])


def test_both_endpoints_read_the_same_kyiv_wall_clock_time() -> None:
    cart = _cart()
    start_kyiv = cart.timeslot_start.astimezone(KYIV)
    end_kyiv = cart.timeslot_end.astimezone(KYIV)

    assert (start_kyiv.hour, start_kyiv.minute) == (3, 30)
    assert (end_kyiv.hour, end_kyiv.minute) == (3, 30)


def test_the_two_endpoints_carry_different_utc_offsets() -> None:
    """This is what makes the wall-clock times equal without the instants
    being equal -- the clock went back by an hour between them."""
    cart = _cart()
    start_offset = cart.timeslot_start.astimezone(KYIV).utcoffset()
    end_offset = cart.timeslot_end.astimezone(KYIV).utcoffset()

    assert start_offset != end_offset


def test_the_window_is_a_real_hour_despite_equal_wall_clock_times() -> None:
    """The instant arithmetic must still give one hour -- comparing UTC
    instants, never the localized wall-clock strings."""
    cart = _cart()
    duration = cart.timeslot_end - cart.timeslot_start

    assert duration.total_seconds() == 3600
