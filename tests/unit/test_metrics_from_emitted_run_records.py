"""G9 (D80, G9.4): the metrics are computed from records a real run
emitted, end to end -- replay -> record -> report.

`compute_metrics.py` shipped with `_load_run_records` returning `[]` and
said so honestly: no run-record format existed, so every metric reported
N/A. G9.3 and G9.6 have now both landed, so the format exists and this
test is what stops the two halves drifting: the emitter lives in
`scripts/core_e2e_repeats.py` and the parser in
`scripts/compute_metrics.py`, and a field renamed on one side without the
other silently returns every metric to N/A -- which looks exactly like
"not measured yet" and would go unnoticed.

Runs the tracked SYNTHETIC bundle through the recorded planner, so this
costs nothing and needs no network.
"""

from pathlib import Path

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.replay import load_bundle, replay
from scripts.compute_metrics import build_metrics_report
from scripts.core_e2e_repeats import build_run_record

BUNDLE = PROJECT_ROOT / "datasets" / "fixtures" / "replay" / "hero_order_cost_min.json"


def _report(tmp_path: Path) -> dict:
    result = replay(load_bundle(BUNDLE))
    record = build_run_record(
        case_id="GD-06", repeat=1, thread_id="t", status="pass", result=result
    )
    import json

    (tmp_path / "g9_run_records_test.json").write_text(
        json.dumps({"records": [record]}), encoding="utf-8"
    )
    report = build_metrics_report(evidence_dir=tmp_path)
    return {m["name"]: m for m in report["metrics"]}


def test_the_journal_denominator_is_not_empty(tmp_path: Path) -> None:
    metrics = _report(tmp_path)
    assert metrics["UnauthorizedWriteRate"]["n"] > 0, (
        "the emitted record carried no journal claims -- the metric is back "
        "to reporting N/A, which reads as 'not measured' rather than a defect"
    )


def test_the_absolute_gates_hold_on_a_real_run(tmp_path: Path) -> None:
    metrics = _report(tmp_path)
    assert metrics["UnauthorizedWriteRate"]["value"] == 0.0
    assert metrics["ReadbackCoverage"]["value"] == 1.0
    assert metrics["ConsentBindingIntegrity"]["value"] == 1.0
    assert metrics["FalseRecovery"]["value"] == 0.0


def test_disclosure_stays_na_because_visibility_was_never_verified(
    tmp_path: Path,
) -> None:
    """A replay cannot audit what the Silpo UI renders, so no row is
    `visibility_verified` -- and the honest answer is N/A, not 0.00."""
    metrics = _report(tmp_path)
    assert metrics["DisclosureRate"]["value"] is None
    assert metrics["DisclosureRate"]["n"] == 0
