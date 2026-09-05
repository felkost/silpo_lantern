"""Render `docs/reports/index.html` — the one part of `docs/` published to
the public repository.

This page is deliberately NOT a stage-by-stage build log: no list of files
written, no decision or amendment ledger, no test-pass counts, no gate
names. Its only job is to show a reader who has never seen the internal
plan **how the system's components interact** (three architecture diagrams,
inlined as SVG so the page needs no network connection) and **why that
interaction is expected to produce a positive, measurable outcome for the
guest and the business**. Everything about how the project got here —
decisions, plan corrections, per-gate evidence — stays in `docs/` locally
and is never read by this script.

Usage: python scripts/render_report.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

ROOT = Path(__file__).resolve().parent.parent
UML_SVG_DIR = ROOT / "docs" / "uml" / "svg"
METRICS_PATH = ROOT / "docs" / "evidence" / "metrics.json"
OUT_PATH = ROOT / "docs" / "reports" / "index.html"

TEMPLATE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Lantern — how it works</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto;
         padding: 0 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.5; }
  h1 { border-bottom: 2px solid #2a5; padding-bottom: .3rem; }
  h2 { margin-top: 2.5rem; }
  .lede { color: #444; font-size: 1.05rem; }
  .diagram { background: white; border: 1px solid #ddd; border-radius: 6px;
             padding: 1rem; margin: 1rem 0; overflow-x: auto; }
  .diagram svg { max-width: 100%; height: auto; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #ccc; padding: .5rem .7rem; text-align: left; }
  th { background: #eee; }
  .pending { color: #a55; font-style: italic; }
  .measured { color: #1a7a1a; font-weight: 600; }
  .meta { color: #888; font-size: .85rem; }
</style></head>
<body>
<h1>Lantern — Checkout Transparency Agent for Silpo</h1>
<p class="lede">How the pieces interact, and why that interaction is expected to help
the guest and the business — not a record of how the project was built.</p>

<h2>1. System architecture</h2>
<p>Six components behind one deployment boundary: the frontend never talks to the MCP
server or the LLM directly; every path to money goes through a single write-authorizing
node.</p>
<div class="diagram">{{ c4_svg }}</div>

<h2>2. The hero recovery flow</h2>
<p>One guest request becomes one traced sequence: read the live cart, diagnose every
blocker the cart already carries, plan candidates backed only by live evidence, get
explicit consent to one specific change, write once, then prove the outcome by an
independent read — never by trusting the write call's own reported success.</p>
<div class="diagram">{{ sequence_svg }}</div>

<h2>3. Safety state machine</h2>
<p>The agent's state graph has a small number of ways in and, more importantly, a small
number of ways to reach a write: an explicit interrupt for consent, a hard stop on any
state change between planning and writing, and a fail-safe "unverified" outcome whenever
the post-write read cannot confirm the result. There is exactly one path through this
graph that ends in a successful receipt, and every other path ends in an honest
non-success.</p>
<div class="diagram">{{ state_svg }}</div>

<h2>4. Why this is expected to help, not just work</h2>
<p>The mechanism above targets a specific, observed gap: the retailer's own MCP server
already returns more structured detail about why a cart is blocked than the shopping
app's screen displays. A cart can carry two independent blocking conditions and the
guest is shown only one message for either of them. Lantern's diagnosis step surfaces
every condition the cart already reports — including the ones the screen never
renders — before proposing any change, and never authorizes a write the guest has not
seen and approved in those exact terms.</p>
<p>The business argument follows the same shape: a cart that reaches checkout is worth
more to the retailer than one abandoned at a blocker, and a guest who understood why
their cart was blocked and fixed it in one step spent less time and fewer actions doing
it than one navigating a generic "add more items" prompt with no further detail.</p>

<h2>5. Measured outcome</h2>
{% if metrics %}
<table>
<tr><th>Metric</th><th>Value</th><th>n</th></tr>
{% for m in metrics %}
<tr><td>{{ m.name }}</td><td class="measured">{{ m.value }}</td><td>{{ m.n }}</td></tr>
{% endfor %}
</table>
{% else %}
<p class="pending">Not yet measured. This section will report recovery completion rate,
median time-to-recovery versus the app, and disclosure rate — each with its sample size,
never as a bare percentage — once moderated before/after testing produces them.</p>
{% endif %}

<p class="meta">Regenerated {{ generated_at }}. No external network resources.</p>
</body></html>
""")


def _inline_svg(name: str) -> str:
    path = UML_SVG_DIR / f"{name}.svg"
    if not path.exists():
        return f"<p><em>Diagram not available locally: {name}.svg</em></p>"
    return path.read_text(encoding="utf-8")


def _load_metrics() -> list[dict] | None:
    if not METRICS_PATH.exists():
        return None
    data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    return data.get("metrics") or None


def render() -> Path:
    html = TEMPLATE.render(
        c4_svg=_inline_svg("c4_container"),
        sequence_svg=_inline_svg("hero_sequence"),
        state_svg=_inline_svg("graph_state"),
        metrics=_load_metrics(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    return OUT_PATH


def main() -> int:
    out_path = render()
    print(f"wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
