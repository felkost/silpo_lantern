"""Render one gate's stage report as a single self-contained HTML file — no
external stylesheets, scripts, or fonts, so it opens in a browser with no
network connection (plan section 19: "один статичний HTML-звіт без
зовнішніх залежностей").

Usage: python scripts/render_report.py --gate S0
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Lantern — {{ gate }} report</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto;
         padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
  h1 { border-bottom: 2px solid #2a5; padding-bottom: .3rem; }
  .status-ok { color: #1a7a1a; font-weight: 600; }
  .status-fail { color: #b00; font-weight: 600; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; }
  th { background: #eee; }
  code { background: #eee; padding: .1rem .3rem; border-radius: 3px; }
  .meta { color: #666; font-size: .9rem; }
</style></head>
<body>
<h1>Lantern — {{ gate }} report</h1>
<p class="meta">Generated {{ generated_at }}. No external network resources used.</p>

<h2>Test summary</h2>
<p>{{ test_summary }}</p>

<h2>Decisions recorded so far</h2>
<table>
<tr><th>ID</th><th>Title</th></tr>
{% for d in decisions %}
<tr><td>{{ d.id }}</td><td>{{ d.title }}</td></tr>
{% endfor %}
</table>

<h2>Plan amendments recorded so far</h2>
<table>
<tr><th>ID</th><th>Title</th></tr>
{% for a in amendments %}
<tr><td>{{ a.id }}</td><td>{{ a.title }}</td></tr>
{% endfor %}
</table>

<h2>Revision decisions</h2>
<p>{{ revision_notes }}</p>
</body></html>
""")


def _run_tests() -> str:
    result = subprocess.run(
        ["pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tail = "\n".join(result.stdout.strip().splitlines()[-5:])
    status = "status-ok" if result.returncode == 0 else "status-fail"
    return f'<span class="{status}">{tail or "(no output)"}</span>'


def _extract_entries(path: Path, heading_pattern: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries = []
    for match in re.finditer(heading_pattern, text, re.MULTILINE):
        entries.append({"id": match.group(1), "title": match.group(2).strip()})
    return entries


def render(gate: str) -> Path:
    decisions = _extract_entries(
        ROOT / "docs" / "decisions.md", r"\*\*(D\d+)\*\*.*?—\s*(.+)"
    )
    amendments = _extract_entries(
        ROOT / "docs" / "plan-amendments.md", r"^## (A\d+) — (.+)$"
    )
    html = TEMPLATE.render(
        gate=gate,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        test_summary=_run_tests(),
        decisions=decisions,
        amendments=amendments,
        revision_notes=(
            "Stage 0 kickoff: scaffold built, no application code yet. "
            "Next gate is G0 (evidence lab), run by hand with the "
            "user's own MCP credentials."
        ),
    )
    out_dir = ROOT / "docs" / "reports" / gate
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True)
    args = parser.parse_args()
    out_path = render(args.gate)
    print(f"wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
