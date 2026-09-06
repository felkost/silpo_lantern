"""DR-09: gap and totals are computed by code; the LLM
only explains and ranks. Enforced two ways: (1) here, a signature check
that `diagnose()` and `compute_order_cost_min_gap()` accept no
externally-suppliable total/gap argument; (2) an extension to
`test_layering.py` flagging any `application`/`interface`-layer function
parameter typed `Gap` or named `*_gap`/`*_total` not sourced from
`Diagnosis` — named here as the declared mechanism the contract this test
checks depends on downstream.
"""

import inspect

from src.lantern.domain.diagnosis import compute_order_cost_min_gap, diagnose


def test_diagnose_accepts_no_precomputed_gap_argument() -> None:
    params = inspect.signature(diagnose).parameters
    assert "gap" not in params
    assert set(params.keys()) == {"cart", "registry"}


def test_compute_order_cost_min_gap_only_accepts_raw_inputs_not_a_gap() -> None:
    params = inspect.signature(compute_order_cost_min_gap).parameters
    assert set(params.keys()) == {"min_order_cost", "products_total"}
