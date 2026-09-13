"""A tracked file may only reference tracked files.
A README pointing at a gitignored spec, or a code comment
citing `insights.md` by date, leads a fresh cloner nowhere. Scans every
git-tracked file's text for a path matching the `docs/*` gitignore rule
(excluding the public exception, the tracked report pages), or a bare
mention of the other gitignored process files
(`handoff.md`, `insights.md`, `CONTRIBUTING.md`).

A bare decision or stage id is just as unresolvable to a fresh clone as a
path is; the second test below flags those too, in every tracked file.
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# The tracked report pages (`docs/reports/*.html`, .gitignore's exception to
# the docs/* rule) are the one kind of docs path a tracked file may name;
# the single index page became six, in two languages.
_GITIGNORED_PATH_PATTERN = re.compile(
    r"\bdocs/(?!reports/(?:uk/)?[A-Za-z0-9_-]+\.html\b)[A-Za-z0-9_./-]+"
)
_GITIGNORED_BARE_FILES = re.compile(r"\b(?:handoff|insights|CONTRIBUTING)\.md\b")

# This test file itself necessarily quotes the patterns it looks for, and
# the .gitignore file is the rule's own source of truth, not a violation
# of it. `evidence_lab.ipynb` tells the runner where to save their OWN
# locally-produced evidence file (`docs/evidence/g0-results.json`) — that
# is an output destination the notebook creates, not a citation pointing a
# fresh cloner at something that should already exist; the CLAUDE.md
# invariant this test enforces is about the latter.
_EXEMPT_FILES = {
    "tests/unit/test_tracked_files_reference_tracked_files.py",
    ".gitignore",
    "notebooks/evidence_lab.ipynb",
}


def _tracked_files() -> list[str]:
    """Files that are tracked **or about to be** — `git ls-files` alone only
    sees what is already committed, so a brand-new file added by the very
    stage this test is meant to police stays invisible to it until after
    the commit that breaks the rule. `--others --exclude-standard` adds the
    untracked-but-not-ignored files, which are exactly the ones the next
    `git add` will promote to tracked.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    about_to_be_tracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = tracked.stdout.splitlines() + about_to_be_tracked.stdout.splitlines()
    return [line for line in lines if line]


def test_no_tracked_file_references_a_gitignored_docs_path() -> None:
    violations: list[str] = []
    for rel_path in _tracked_files():
        if rel_path in _EXEMPT_FILES:
            continue
        full_path = PROJECT_ROOT / rel_path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary tracked file (e.g. a PNG) — not a text reference

        for match in _GITIGNORED_PATH_PATTERN.finditer(text):
            violations.append(f"{rel_path}: references {match.group(0)!r}")

        for match in _GITIGNORED_BARE_FILES.finditer(text):
            violations.append(f"{rel_path}: references {match.group(0)!r}")

    assert not violations, "\n".join(violations)


# A stage id (`G8`), a decision id (`D42`, `D-G10-03`) or an amendment id
# (`A-G10-02`) names an entry in the decision log or a stage plan, and both
# live outside the repository. To a fresh clone every one of them is a
# dangling reference, wherever it sits -- a code comment, a schema
# description, a fixture's provenance string, the console's own text or a
# diagram inlined into the site -- so every tracked text file is scanned.
_STAGE_OR_DECISION_ID = re.compile(
    r"\b(?:D-?G?\d{1,3}|G\d{1,2}(?:\+G\d{1,2})?|A-G\d+)\b"
)


def test_no_tracked_file_carries_a_stage_or_decision_id() -> None:
    violations: list[str] = []
    for rel_path in _tracked_files():
        if rel_path in _EXEMPT_FILES:
            continue
        full_path = PROJECT_ROOT / rel_path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in _STAGE_OR_DECISION_ID.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{rel_path}:{line}: {match.group(0)!r}")
    assert not violations, "\n".join(violations)


# Beyond bare ids, the words that only mean something next to the plan or
# the local-only process documents: a plan section citation, an "IV-05"
# infrastructure item, "kickoff", "this stage", "the stage report", an
# amendment id, the name of a gitignored process file, or the "donor"
# project the reused components came from. Each one sends a fresh clone
# looking for a document that is not there. The SSE event named `stage`
# and the graph node named `plan` are product vocabulary and are not
# matched: only the plan-citation and stage-of-work phrasings are.
_PLAN_VOCABULARY = re.compile(
    r"[Pp]lan (?:section|\u00a7)\s?\d"
    r"|\u00a7\s?\d"
    r"|\bIV-\d{1,2}\b"
    r"|\bkickoff\b"
    r"|\b(?:this|an earlier|a later|later|earlier) stages?\b"
    r"|\bstage (?:reports?|specs?|plans?|close)\b"
    r"|\bamendment A\d+\b"
    r"|\b(?:CLAUDE|AGENTS|AI_USAGE|BACKGROUND_MATERIALS|THIRD_PARTY_NOTICES)(?:\.md)?\b"
    r"|\bdonor\b"
    r"|\bSupportFlow\b"
)

_VOCABULARY_EXEMPT = {
    "tests/unit/test_tracked_files_reference_tracked_files.py",
    ".gitignore",
}


def test_no_tracked_file_carries_plan_or_stage_vocabulary() -> None:
    violations: list[str] = []
    for rel_path in _tracked_files():
        if rel_path in _VOCABULARY_EXEMPT:
            continue
        full_path = PROJECT_ROOT / rel_path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in _PLAN_VOCABULARY.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{rel_path}:{line}: {match.group(0)!r}")
    assert not violations, "\n".join(violations)
