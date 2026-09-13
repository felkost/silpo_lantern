"""runs every `not_run` row of the RG coverage map and
keeps the pytest output as the run artefact the brief requires
before a row may read `pass`. The tests already exist and pass in the
gate; what was missing was a RECORDED run naming which node ids ran,
when, on which commit, with what result -- the map's own test
(`test_rg_coverage_map_is_honest.py`) refuses `pass` without one.

    .venv/Scripts/python.exe scripts/record_rg_runs.py

Writes `datasets/golden-v1.0.0/rg_runs/rg_runs_<UTC>.json` and prints, per row, the
verdict to paste into `coverage.json`. It does NOT edit the map: promotion
is a reviewed edit, and `RG-05` (blocked) and `RG-06`
(not_applicable) are never run here.
"""

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lantern.config import PROJECT_ROOT  # noqa: E402

COVERAGE = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "coverage.json"
# Beside the map it promotes, and TRACKED -- `datasets/evidence/` is gitignored,
# and a tracked coverage.json may not point at a file a clone does not have.
RUNS_DIR = COVERAGE.parent / "rg_runs"


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _run(node_ids: List[str]) -> Dict[str, Any]:
    # `-p no:cacheprovider`: a run artefact must not depend on, or write,
    # the pytest cache of whoever ran it last.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *node_ids],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return {
        "node_ids": node_ids,
        "returncode": result.returncode,
        "summary": summary,
        "stdout_tail": result.stdout[-1500:],
        "verdict": "pass" if result.returncode == 0 else "fail",
    }


def main() -> int:
    rows = json.loads(COVERAGE.read_text(encoding="utf-8"))["rows"]
    started = datetime.now(timezone.utc)
    runs = {
        row["rg_id"]: _run(row["node_ids"])
        for row in rows
        if row["status"] == "not_run"
    }
    artefact = {
        "recorded_at": started.isoformat(),
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "command": "python scripts/record_rg_runs.py",
        "runs": runs,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNS_DIR / f"rg_runs_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(artefact, indent=2, ensure_ascii=False), encoding="utf-8")
    for rg_id, run in runs.items():
        print(f"{rg_id}: {run['verdict']}  ({run['summary']})")
    print(f"artefact: {out.relative_to(PROJECT_ROOT)}")
    return 0 if all(r["verdict"] == "pass" for r in runs.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
