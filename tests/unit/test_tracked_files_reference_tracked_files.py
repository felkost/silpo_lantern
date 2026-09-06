"""D-G3-08/G3-F18/CLAUDE.md invariant: "A tracked file may only reference
tracked files." A README pointing at a gitignored spec, or a code comment
citing `insights.md` by date, leads a fresh cloner nowhere. Scans every
git-tracked file's text for a path matching the `docs/*` gitignore rule
(excluding the one public exception, `docs/reports/index.html`), or a bare
mention of the other gitignored process files
(`handoff.md`, `insights.md`).

Stable ids (`D-G1-04`, `F7`, `D12`) are the correct way to cite a decision
or finding from tracked code — this test does not flag those, only literal
paths into files a fresh clone will not have.
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# docs/reports/index.html is the one tracked exception to the docs/*
# gitignore rule (.gitignore) — a reference to it is fine.
_ALLOWED_DOCS_PATH = "docs/reports/index.html"

_GITIGNORED_PATH_PATTERN = re.compile(
    r"\bdocs/(?!reports/index\.html\b)[A-Za-z0-9_./-]+"
)
_GITIGNORED_BARE_FILES = re.compile(r"\b(?:handoff|insights)\.md\b")

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
            if match.group(0) == _ALLOWED_DOCS_PATH:
                continue
            violations.append(f"{rel_path}: references {match.group(0)!r}")

        for match in _GITIGNORED_BARE_FILES.finditer(text):
            violations.append(f"{rel_path}: references {match.group(0)!r}")

    assert not violations, "\n".join(violations)
