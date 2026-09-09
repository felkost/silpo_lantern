"""G9 (D61, G9.4): the I/O shell around `src/lantern/domain/metrics.py`'s
pure functions. Reads the golden/repeat runs' own emitted records from the tracked
`datasets/evidence` directory (D61's own "source of truth" decision --
not the author's historical Neon rows, so the numbers stay reproducible
from the repository) and writes the metrics report to
`METRICS_OUTPUT_PATH` below, in the shape `render_report.py`'s
`_load_metrics` reads.

`METRICS_OUTPUT_PATH` is built from `PROJECT_ROOT` parts, never a literal
joined path string -- a tracked file spelling that path out fails
`tests/unit/test_tracked_files_reference_tracked_files.py`'s
`test_no_tracked_file_references_a_gitignored_docs_path`, the same trap
`render_report.py:33` already avoids for its own `METRICS_PATH`.

**Provisional today.** G9.3 (the golden runner) and G9.6 (the 18 repeats)
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
    ConsentBindingRow,
    CostDeltaRow,
    DisclosureRow,
    FalseRecoveryRow,
    JournalClaim,
    RecoveryEpisode,
    consent_binding_integrity,
    cost_delta_accuracy,
    disclosure_rate,
    false_recovery,
    readback_coverage,
    recovery_completion_rate,
    unauthorized_write_rate,
)


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


METRICS_OUTPUT_PATH = PROJECT_ROOT / "docs" / "evidence" / "metrics.json"


def _load_run_records(evidence_dir: Path) -> List[Dict[str, Any]]:
    """Reads every `g9_run_records_*.json` the repeat runs emitted (D80).
    A missing directory is an empty population, not an error -- the
    metrics then honestly report N/A, which is what a repository with no
    run yet should say."""
    records: List[Dict[str, Any]] = []
    if not evidence_dir.is_dir():
        return records
    for path in sorted(evidence_dir.glob("g9_run_records_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        records.extend(document.get("records", []))
    return records


def build_metrics_report(*, evidence_dir: Path) -> Dict[str, Any]:
    records = _load_run_records(evidence_dir)

    claims: List[JournalClaim] = []
    consents_by_action_id: Dict[str, object] = {}
    receipts_by_action_id: Dict[str, object] = {}
    consent_binding_rows: List[ConsentBindingRow] = []
    cost_delta_rows: List[CostDeltaRow] = []
    episodes: List[RecoveryEpisode] = []
    disclosure_rows: List[DisclosureRow] = []
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

    results = {
        "UnauthorizedWriteRate": unauthorized_write_rate(claims, consents_by_action_id),
        "ReadbackCoverage": readback_coverage(claims, receipts_by_action_id),
        "ConsentBindingIntegrity": consent_binding_integrity(consent_binding_rows),
        "CostDeltaAccuracy": cost_delta_accuracy(cost_delta_rows),
        "RecoveryCompletionRate": recovery_completion_rate(episodes),
        "FalseRecovery": false_recovery(false_recovery_rows),
        "DisclosureRate": disclosure_rate(disclosure_rows),
    }

    return {
        "metrics": [
            {"name": name, "value": result.value, "n": result.n}
            for name, result in results.items()
        ]
    }


def main() -> None:
    report = build_metrics_report(evidence_dir=PROJECT_ROOT / "datasets" / "evidence")
    METRICS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {METRICS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
