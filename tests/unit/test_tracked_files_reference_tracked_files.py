"""A tracked file may only reference tracked files.
A README pointing at a gitignored spec, or a code comment
citing `insights.md` by date, leads a fresh cloner nowhere. Scans every
git-tracked file's text for a path matching the `docs/*` gitignore rule
(excluding the public exception, the tracked report pages), or a bare
mention of the other gitignored process files
(`handoff.md`, `insights.md`, `CONTRIBUTING.md`).

Historically this project treated a stable id (`D-G1-04`, `F7`, `D12`) as an
acceptable citation from tracked code, since it names a decision rather than a
literal path. Practice has moved past that: a bare id is just as unresolvable
to a fresh clone as a path is, and G4's own cleanup removed the ones that had
crept in — this test still does not flag a bare id (checking every possible
citation pattern this way would be unreliably broad), but new code should
prefer a self-contained comment over a citation of either kind.
"""

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# The tracked report pages (`docs/reports/*.html`, .gitignore's exception to
# the docs/* rule) are the one kind of docs path a tracked file may name;
# G10 split the single index page into six, in two languages.
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


# A reader of the public surfaces -- the documentation site, the README, the
# console's own text and the diagrams inlined into the site -- has no
# decision log or stage plan to look ids up in, so a bare `D42`, `D-G10-03`
# or `G8` there is a dangling reference. Code comments are policed by review
# (the docstring above says why a blanket rule is unreliable); these
# surfaces are scanned because a reader cannot skip them.
_STAGE_OR_DECISION_ID = re.compile(
    r"\b(?:D-?G?\d{1,3}|G\d{1,2}(?:\+G\d{1,2})?|A-G\d+)\b"
)
_JS_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def _reader_facing_files() -> list[str]:
    files = []
    for rel_path in _tracked_files():
        if rel_path == "README.md" or rel_path.startswith("scripts/report_content_"):
            files.append(rel_path)
        elif rel_path.startswith("docs/reports/") and rel_path.endswith(".html"):
            files.append(rel_path)
        elif (
            rel_path.startswith("apps/web/src/")
            and rel_path.endswith((".ts", ".tsx"))
            and ".test." not in rel_path
        ):
            files.append(rel_path)
    return files


def test_reader_facing_surfaces_carry_no_stage_or_decision_ids() -> None:
    violations: list[str] = []
    for rel_path in _reader_facing_files():
        text = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")
        if rel_path.endswith((".ts", ".tsx")):
            text = _JS_COMMENTS.sub("", text)
        for match in _STAGE_OR_DECISION_ID.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{rel_path}:{line}: {match.group(0)!r}")
    assert not violations, "\n".join(violations)
