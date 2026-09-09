"""DisclosureRate's population is the UI audit, not the replay runs.

Every replayed run emits a disclosure row with `visibility_verified:
false` -- a replay cannot audit what the Silpo app renders, and saying so
is the honest record. But those rows are all excluded, so with only them
the metric is permanently N/A no matter how many runs happen.

The population is `datasets/golden-v1.0.0/disclosure_audit/
observations.json`: rows a person produced by looking at the app, tracked
because they cannot be regenerated.

The metric's own rule survives unchanged here: a row is counted only when
`visibility_verified` is true, and an unverified row is never folded into
"not hidden" by a `bool(None)` shortcut -- unknown is not the same as
disclosed.
"""

import json
from pathlib import Path

from scripts.compute_metrics import _load_disclosure_rows, build_metrics_report


def _write(directory: Path, rows: list) -> Path:
    audit = directory / "disclosure_audit"
    audit.mkdir(parents=True, exist_ok=True)
    path = audit / "observations.json"
    path.write_text(json.dumps({"observations": rows}), encoding="utf-8")
    return path


def test_a_verified_hidden_constraint_is_counted(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [
            {
                "state_id": "1",
                "visibility_verified": True,
                "had_invisible_constraint": True,
            }
        ],
    )

    rows = _load_disclosure_rows(tmp_path)

    assert len(rows) == 1
    assert rows[0].visibility_verified is True
    assert rows[0].had_invisible_constraint is True


def test_an_unverified_row_is_carried_but_never_counted(tmp_path: Path) -> None:
    """It must reach the metric, which excludes it -- dropping it here
    would hide that the observation was attempted at all."""
    _write(
        tmp_path,
        [
            {
                "state_id": "1",
                "visibility_verified": True,
                "had_invisible_constraint": True,
            },
            {
                "state_id": "2",
                "visibility_verified": False,
                "had_invisible_constraint": None,
            },
        ],
    )

    rows = _load_disclosure_rows(tmp_path)

    assert len(rows) == 2
    assert sum(1 for r in rows if r.visibility_verified) == 1


def test_a_missing_audit_is_an_empty_population_not_an_error(tmp_path: Path) -> None:
    assert _load_disclosure_rows(tmp_path) == []


def test_the_real_audit_reaches_the_report() -> None:
    """The tracked audit is the one the published number comes from."""
    from src.lantern.config import PROJECT_ROOT

    report = build_metrics_report(
        evidence_dir=PROJECT_ROOT / "datasets" / "evidence",
        golden_dir=PROJECT_ROOT / "datasets" / "golden-v1.0.0",
    )
    disclosure = next(m for m in report["metrics"] if m["name"] == "DisclosureRate")

    assert disclosure["n"] >= 1, (
        "the tracked UI audit is not reaching the metric -- DisclosureRate "
        "would keep reporting N/A with observations sitting on disk"
    )
