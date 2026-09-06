"""A naive (offset-less) datetime is rejected rather than silently
assumed UTC. `datetime.fromisoformat` on an offset-less string returns
naive with no error, and treating an already-expired slot as still live is
the worst possible failure direction.
"""

from datetime import datetime

import pytest

from src.lantern.domain.normalizer import CartShapeError, to_kyiv_display


def test_naive_datetime_raises() -> None:
    naive = datetime.fromisoformat("2026-08-13T06:30:00")
    with pytest.raises(CartShapeError):
        to_kyiv_display(naive)


def test_aware_datetime_passes_through() -> None:
    aware = datetime.fromisoformat("2026-08-13T06:30:00+00:00")
    assert to_kyiv_display(aware) is aware
