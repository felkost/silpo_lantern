"""the RG coverage map may not claim anything it
cannot back.

This is the test the initial review's finding motivates: five RG
rows had been claimed `pass` on the strength of topically-related tests
that did not exercise the rubric. A coverage map is worth less than
nothing if it can say `pass` without a run artefact -- it converts an
unknown into a false assurance.

Enforced here:
  * every named pytest node id resolves to something pytest can collect;
  * every RG id appears exactly once, and all of RG-01..07 are present;
  * no row says `pass` without a run artefact;
  * `not_applicable` appears on RG-06 only -- the one row the brief
    itself defers (RAG);
  * a row naming an integration-only node id is `blocked` when
    DATABASE_URL is unset, never silently `pass`.
"""

import json
import os
import subprocess
import sys

from src.lantern.config import PROJECT_ROOT

COVERAGE_PATH = PROJECT_ROOT / "datasets" / "golden-v1.0.0" / "coverage.json"

EXPECTED_RG_IDS = {f"RG-0{n}" for n in range(1, 8)}
VALID_STATUSES = {"not_run", "blocked", "not_applicable", "pass"}


def _rows():
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))["rows"]


def test_every_rg_id_appears_exactly_once() -> None:
    ids = [row["rg_id"] for row in _rows()]
    assert sorted(ids) == sorted(EXPECTED_RG_IDS)
    assert len(ids) == len(set(ids)), "an RG id is listed twice"


def test_every_status_is_one_of_the_declared_four() -> None:
    for row in _rows():
        assert row["status"] in VALID_STATUSES, row


def test_no_row_claims_pass_without_a_run_artefact() -> None:
    """the brief, verbatim: a new test's status before it runs is
    `not_run`, never `pass`. A `pass` must name the artefact that backs
    it."""
    for row in _rows():
        if row["status"] == "pass":
            assert row.get("run_artefact"), (
                f"{row['rg_id']} claims pass with no run_artefact -- exactly "
                "the overstatement this file exists to prevent"
            )


def test_not_applicable_is_used_only_for_the_row_the_brief_defers() -> None:
    for row in _rows():
        if row["status"] == "not_applicable":
            assert row["rg_id"] == "RG-06", (
                f"{row['rg_id']} is marked not_applicable, but the brief "
                "defers only RG-06 (RAG). Every other rubric is MVP-active: "
                "an untestable one is `blocked` with a reason, never excused."
            )


def test_every_row_states_a_reason() -> None:
    for row in _rows():
        assert row.get("reason", "").strip(), f"{row['rg_id']} states no reason"


def _collection_report(node_ids) -> str:
    """Collects the given node ids in ONE pytest subprocess (fast enough
    for the gate) and returns its combined output.

    Deliberately NOT checked by return code: pytest exits 0 for a node id
    that matches nothing, printing "no match in any of ..." and
    "no tests collected". A return-code check therefore passes for a
    completely bogus id -- caught while writing this file, by running a
    made-up node id and watching the check stay green.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *node_ids],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return f"{result.stdout}\n{result.stderr}"


def _looks_unresolved(report: str) -> bool:
    return "no match in any of" in report or "no tests collected" in report


def test_every_named_node_id_resolves() -> None:
    """A node id that does not resolve is a coverage claim pointing at
    nothing."""
    node_ids = [nid for row in _rows() for nid in row["node_ids"]]
    assert node_ids, "the map names no tests at all"

    report = _collection_report(node_ids)
    assert not _looks_unresolved(report), (
        "at least one node id in coverage.json resolves to nothing:\n"
        f"{report[-2000:]}"
    )


def test_the_resolution_check_actually_fires_on_a_bogus_node_id() -> None:
    """Proves the check above is not vacuous -- the project's own
    synthetic-violation practice. A made-up node id must be reported
    unresolved, even though pytest exits 0 for it."""
    report = _collection_report(
        ["tests/unit/test_rg_fault_injection.py::test_this_does_not_exist"]
    )
    assert _looks_unresolved(report)


def test_an_integration_only_row_is_blocked_without_a_database() -> None:
    """`tests/integration/**` skips without DATABASE_URL, so a row resting
    on one cannot honestly read `pass` in an environment that never ran
    it."""
    if os.environ.get("DATABASE_URL"):
        return
    for row in _rows():
        rests_on_integration = any(
            nid.startswith("tests/integration/") for nid in row["node_ids"]
        )
        if rests_on_integration:
            assert row["status"] in ("blocked", "not_run"), (
                f"{row['rg_id']} rests on an integration-only test but reads "
                f"{row['status']!r} with no DATABASE_URL in the environment"
            )


def test_a_pass_row_names_an_artefact_git_tracks() -> None:
    """A tracked file may only reference tracked files (the project invariants): a
    `run_artefact` under a gitignored directory is a claim a fresh clone
    cannot check. Caught delivery B, where the first recorder wrote
    into `datasets/evidence/`, which `.gitignore` excludes."""
    for row in _rows():
        if row["status"] != "pass":
            continue
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", row["run_artefact"]],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert (
            tracked.returncode == 0
        ), f"{row['rg_id']}'s run_artefact {row['run_artefact']!r} is not tracked"
