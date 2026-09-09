"""T17 (G9 spec): `compute_metrics.py` emits every metric in G9.4's table
in the exact shape `render_report.py:336`'s `_load_metrics` reads
(`data["metrics"]`, a list of `{name, value, n}` objects), writes to a
`PROJECT_ROOT`-derived path (never the literal gitignored docs path a
tracked file may not reference), and leaves the golden dataset's own
evidence directory untouched when no run records exist yet -- an honest
all-N/A report, not a fabricated one.
"""

import json

from src.lantern.config import PROJECT_ROOT
from scripts.compute_metrics import METRICS_OUTPUT_PATH, build_metrics_report

# D82: `CostDeltaAccuracy` (plan section 13.3's name) became TWO entries.
# It compared the recorded delta against the price the product SEARCH
# advertised and was gated at "exact" -- on an assumption D68 disproved,
# since the cart applies a per-product loyalty discount the search does
# not carry (D76). One question was really two:
#
#   WriteDeltaFidelity  -- recorded delta vs the cart's own before/after
#                          movement. Ours, gated 1.00 absolute.
#   SearchPriceFidelity -- the original computation, unchanged, reported
#                          without a gate as the observation of Silpo's
#                          pricing that it is.
#
# The 0.455 figure is relabelled, never deleted.
EXPECTED_METRIC_NAMES = {
    "UnauthorizedWriteRate",
    "ReadbackCoverage",
    "ConsentBindingIntegrity",
    "WriteDeltaFidelity",
    "SearchPriceFidelity",
    "RecoveryCompletionRate",
    "FalseRecovery",
    "DisclosureRate",
}


def test_output_path_is_built_from_project_root() -> None:
    assert METRICS_OUTPUT_PATH == PROJECT_ROOT / "docs" / "evidence" / "metrics.json"


def test_report_shape_matches_what_render_report_reads() -> None:
    report = build_metrics_report(evidence_dir=PROJECT_ROOT / "datasets" / "evidence")

    assert "metrics" in report
    names = {m["name"] for m in report["metrics"]}
    assert EXPECTED_METRIC_NAMES <= names
    for metric in report["metrics"]:
        assert set(metric.keys()) == {"name", "value", "n"}


def test_an_empty_evidence_population_reports_every_metric_as_not_applicable(
    tmp_path,
) -> None:
    empty_dir = tmp_path / "no_evidence_here"
    empty_dir.mkdir()

    report = build_metrics_report(evidence_dir=empty_dir)

    for metric in report["metrics"]:
        assert metric["value"] is None
        assert metric["n"] == 0


def test_report_is_json_serializable() -> None:
    report = build_metrics_report(evidence_dir=PROJECT_ROOT / "datasets" / "evidence")
    json.dumps(report)  # raises if anything (e.g. a bare Decimal) leaks through
