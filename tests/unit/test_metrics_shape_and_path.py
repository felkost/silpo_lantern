"""`compute_metrics.py` emits every metric in the table
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

# `CostDeltaAccuracy` (the brief's name) became TWO entries.
# It compared the recorded delta against the price the product SEARCH
# advertised and was gated at "exact" -- on an assumption an earlier decision disproved,
# since the cart applies a per-product loyalty discount the search does
# not carry. One question was really two:
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
    # the console may show no proportion without its interval and
    # its caveat, so the report carries both from the source.
    for metric in report["metrics"]:
        assert set(metric.keys()) == {"name", "value", "n", "interval", "caveat"}


def test_an_empty_population_reports_every_metric_as_not_applicable(
    tmp_path,
) -> None:
    """Empty means BOTH sources empty. DisclosureRate does not read the
    run records -- a replay cannot audit what the Silpo app renders -- so
    it comes from the tracked UI audit instead, and an empty evidence
    directory alone no longer empties it. Pointing this test only at the
    evidence directory would have it assert that a real, tracked
    observation does not exist."""
    empty_evidence = tmp_path / "no_evidence_here"
    empty_evidence.mkdir()
    empty_golden = tmp_path / "no_golden_here"
    empty_golden.mkdir()

    report = build_metrics_report(evidence_dir=empty_evidence, golden_dir=empty_golden)

    for metric in report["metrics"]:
        assert metric["value"] is None
        assert metric["n"] == 0


def test_the_tracked_audit_survives_an_empty_evidence_directory(tmp_path) -> None:
    """The other half of the rule above: with no run records at all, the
    UI audit still reports, because it is a different population and not
    a by-product of running the graph."""
    empty_evidence = tmp_path / "no_evidence_here"
    empty_evidence.mkdir()

    report = build_metrics_report(evidence_dir=empty_evidence)
    disclosure = next(m for m in report["metrics"] if m["name"] == "DisclosureRate")

    assert disclosure["n"] >= 1


def test_report_is_json_serializable() -> None:
    report = build_metrics_report(evidence_dir=PROJECT_ROOT / "datasets" / "evidence")
    json.dumps(report)  # raises if anything (e.g. a bare Decimal) leaks through
