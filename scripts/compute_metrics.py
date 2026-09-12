"""the I/O shell around `src/lantern/domain/metrics.py`'s
pure functions. Reads the golden/repeat runs' own emitted records from the tracked
`datasets/evidence` directory (the own "source of truth" decision --
not the author's historical Neon rows, so the numbers stay reproducible
from the repository) and writes the metrics report to
`METRICS_OUTPUT_PATH` below, in the shape `render_report.py`'s
`_load_metrics` reads.

`METRICS_OUTPUT_PATH` is built from `PROJECT_ROOT` parts, never a literal
joined path string -- a tracked file spelling that path out fails
`tests/unit/test_tracked_files_reference_tracked_files.py`'s
`test_no_tracked_file_references_a_gitignored_docs_path`, the same trap
`render_report.py:33` already avoids for its own `METRICS_PATH`.

**Provisional today.** The golden runner and the 18 repeats
have not landed yet, so no run-record file format exists to load from --
`_load_run_records` below returns an empty list rather than inventing a
schema for data that has never been emitted, per this project's own rule
against inventing a plausible-looking value. Every metric therefore
reports N/A (`value: None, n: 0`) until those stages populate
`datasets/evidence/`. This is an honest report of "not yet measured", not
a placeholder pretending to be a result.
"""

from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.lantern.config import PROJECT_ROOT
from src.lantern.domain.metrics import (
    COUNT_METRICS,
    METRIC_CAVEATS,
    ConsentBindingRow,
    CostDeltaRow,
    DisclosureRow,
    FalseRecoveryRow,
    JournalClaim,
    RecoveryEpisode,
    WriteDeltaRow,
    consent_binding_integrity,
    cost_delta_accuracy,
    disclosure_rate,
    false_recovery,
    readback_coverage,
    recovery_completion_rate,
    unauthorized_write_rate,
    wilson,
    write_delta_fidelity,
)


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


METRICS_OUTPUT_PATH = PROJECT_ROOT / "docs" / "evidence" / "metrics.json"
# the console's source. `docs/` is gitignored, so the deployed service
# has no `METRICS_OUTPUT_PATH`; this copy is tracked, regenerated from the
# tracked bundles alone (`--tracked`), and pinned by an agreement test.
TRACKED_METRICS_PATH = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "metrics.json"


def _load_run_records(
    evidence_dir: Path, population: str = "offline"
) -> List[Dict[str, Any]]:
    """Reads the repeat runs' emitted records for ONE population.

    Both configurations write `g9_run_records_*.json` into the same
    directory, so globbing the pattern merged them: running the offline
    and live repeats once each doubled every denominator from 33 to 66
    and produced numbers describing neither population. Nothing would have
    flagged it -- the values stay 1.00 and 0.00 either way.

    A missing directory is an empty population, not an error. A file that
    declares no population is an error: guessing which one it belongs to
    is exactly the silent merge this exists to prevent.
    """
    records: List[Dict[str, Any]] = []
    if not evidence_dir.is_dir():
        return records
    for path in sorted(evidence_dir.glob("g9_run_records_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        declared = document.get("population")
        if declared is None:
            raise ValueError(
                f"{path.name} declares no population -- it predates that field and "
                "cannot be assigned to one without guessing"
            )
        if declared == population:
            records.extend(document.get("records", []))
    return records


def _load_disclosure_rows(golden_dir: Path) -> List[DisclosureRow]:
    """DisclosureRate's population: the UI audit, not the replay runs.

    A replay cannot see what the Silpo app renders, so every run record
    carries `visibility_verified: false` and is correctly excluded -- with
    only those, the metric is permanently N/A however many runs happen.
    The rows that can answer the question are produced by a person looking
    at the app, under `disclosure_audit/`, and are tracked because they
    cannot be regenerated.

    Unverified rows are loaded rather than dropped: the metric excludes
    them itself, and dropping them here would erase the fact that the
    observation was attempted.
    """
    path = golden_dir / "disclosure_audit" / "observations.json"
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    return [
        DisclosureRow(
            had_invisible_constraint=row.get("had_invisible_constraint"),
            visibility_verified=bool(row.get("visibility_verified")),
        )
        for row in document.get("observations", [])
    ]


def build_metrics_report(
    *,
    evidence_dir: Path,
    population: str = "offline",
    golden_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    records = _load_run_records(evidence_dir, population)
    golden_dir = golden_dir or (PROJECT_ROOT / "datasets" / "golden-v1.0.0")

    claims: List[JournalClaim] = []
    consents_by_action_id: Dict[str, object] = {}
    receipts_by_action_id: Dict[str, object] = {}
    consent_binding_rows: List[ConsentBindingRow] = []
    cost_delta_rows: List[CostDeltaRow] = []
    episodes: List[RecoveryEpisode] = []
    disclosure_rows: List[DisclosureRow] = []
    write_delta_rows: List[WriteDeltaRow] = []
    false_recovery_rows: List[FalseRecoveryRow] = []

    for record in records:
        # One episode per run: plan section 13.1's unit is the
        # participant/cart/task/condition, and the three repeats of a case
        # are three episodes, not one retried.
        episodes.append(RecoveryEpisode(completed=bool(record.get("completed"))))

        consent_ids = set(record.get("consent_action_ids") or [])
        for claim in record.get("journal_claims") or []:
            claims.append(
                JournalClaim(
                    owner=claim["owner"],
                    cart_id=claim["cart_id"],
                    action_id=claim["action_id"],
                    state=claim["state"],
                )
            )
        consents_by_action_id.update({action_id: True for action_id in consent_ids})

        for receipt in record.get("receipts") or []:
            receipts_by_action_id[receipt["action_id"]] = True
            false_recovery_rows.append(
                FalseRecoveryRow(
                    claimed_blocker_cleared=bool(receipt["claimed_blocker_cleared"]),
                    actually_cleared=bool(receipt["actually_cleared"]),
                )
            )
            cost_delta_rows.append(
                CostDeltaRow(
                    kind=receipt.get("kind", "add"),
                    expected_delta=_decimal_or_none(receipt.get("expected_delta")),
                    actual_delta=_decimal_or_none(receipt.get("actual_delta")),
                )
            )
            cart_delta = receipt.get("cart_delta")
            if cart_delta is not None:
                write_delta_rows.append(
                    WriteDeltaRow(
                        actual_delta=_decimal_or_none(receipt.get("actual_delta")),
                        cart_delta=Decimal(str(cart_delta)),
                    )
                )
            consented = receipt.get("consented_args_hash")
            written = receipt.get("written_args_hash")
            if consented is not None and written is not None:
                consent_binding_rows.append(
                    ConsentBindingRow(
                        consented_args_hash=consented, written_args_hash=written
                    )
                )

        disclosure = record.get("disclosure") or {}
        disclosure_rows.append(
            DisclosureRow(
                had_invisible_constraint=disclosure.get("had_invisible_constraint"),
                visibility_verified=bool(disclosure.get("visibility_verified")),
            )
        )

    # The rows that can actually answer the question (see the loader).
    disclosure_rows.extend(_load_disclosure_rows(golden_dir))

    results = {
        "UnauthorizedWriteRate": unauthorized_write_rate(claims, consents_by_action_id),
        "ReadbackCoverage": readback_coverage(claims, receipts_by_action_id),
        "ConsentBindingIntegrity": consent_binding_integrity(consent_binding_rows),
        # what WE control -- the recorded delta against the cart's
        # own movement. Gated at 1.00 absolute.
        "WriteDeltaFidelity": write_delta_fidelity(write_delta_rows),
        # section 13.3's `CostDeltaAccuracy`, unchanged in
        # computation and renamed for what it actually measures -- how
        # well the SEARCH price predicts the price the cart charges.
        # Reported without a gate: it is an observation of Silpo's
        # discount policy, not of this system's behaviour.
        "SearchPriceFidelity": cost_delta_accuracy(cost_delta_rows),
        "RecoveryCompletionRate": recovery_completion_rate(episodes),
        "FalseRecovery": false_recovery(false_recovery_rows),
        "DisclosureRate": disclosure_rate(disclosure_rows),
    }

    return {
        "metrics": [
            {
                "name": name,
                "value": result.value,
                "n": result.n,
                # the interval and the caveat travel WITH the number,
                # so no surface can render one without the other.
                "interval": (
                    None
                    if name in COUNT_METRICS or result.value is None
                    else [round(x, 4) for x in wilson(result.value, result.n)]
                ),
                "caveat": METRIC_CAVEATS[name],
            }
            for name, result in results.items()
        ]
    }


def build_tracked_metrics_report() -> Dict[str, Any]:
    """The report a fresh clone can reproduce: the 18 offline repeats over
    the tracked bundles, in memory, then the same computation as the
    evidence-directory path. ~3 s. `generated_at` is the only field two
    runs differ in."""
    import tempfile
    from datetime import datetime, timezone

    from scripts.core_e2e_repeats import run_repeats

    repeats = run_repeats(estimate_only=False, offline=True)
    with tempfile.TemporaryDirectory() as tmp:
        records = Path(tmp) / "g9_run_records_offline.json"
        records.write_text(
            json.dumps({"population": "offline", "records": repeats["records"]}),
            encoding="utf-8",
        )
        report = build_metrics_report(evidence_dir=Path(tmp))
    return {
        "population": "offline",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regenerate": "python -m scripts.compute_metrics --tracked",
        **report,
    }


def main() -> None:
    import sys

    if "--tracked" in sys.argv:
        TRACKED_METRICS_PATH.write_text(
            json.dumps(build_tracked_metrics_report(), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {TRACKED_METRICS_PATH.relative_to(PROJECT_ROOT)}")
        return
    report = build_metrics_report(evidence_dir=PROJECT_ROOT / "datasets" / "evidence")
    METRICS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {METRICS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
