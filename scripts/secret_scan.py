"""Scan every tracked-or-trackable file for likely secrets before it can leak
into a public repository (IV-03: "Жодного токена в клієнті/логах/репозиторії").

Uses `git ls-files --cached --others --exclude-standard` rather than reading
the working directory directly, so a file `.gitignore` already excludes
(.env, .cache/, notebook outputs) is never scanned or flagged — the guard
follows the same boundary the repository itself enforces, not a separate
list that can drift from it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Patterns tuned for false-negative avoidance over false-positive avoidance:
# a missed secret is a real leak, a flagged .env.example placeholder is a
# ten-second read. Each pattern names what it is meant to catch.
PATTERNS: dict[str, re.Pattern[str]] = {
    "OpenAI-style API key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "AWS access key id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic bearer token assignment": re.compile(
        r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?"
    ),
    "OAuth client secret shape": re.compile(r"(?i)client_secret\s*[:=]\s*\S{16,}"),
}

# Files where a matching-looking string is expected and safe: placeholder
# names, not real values. Extend this list only for genuinely-empty templates.
ALLOWLIST_FILES = {".env.example"}

# A value that is just the key name with no assignment (KEY=) is not a leak.
EMPTY_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*(['\"]?['\"]?)?$"
)


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [root / line for line in result.stdout.splitlines() if line]


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in _tracked_files(root):
        if path.name in ALLOWLIST_FILES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if EMPTY_ASSIGNMENT.search(line):
                continue
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(root)}:{line_no}: {name}")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    findings = scan(root)
    if findings:
        print(f"secret-scan: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("secret-scan: 0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
