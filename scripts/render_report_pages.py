"""Renders the four focused report pages the README links to -- the hero
run, safety, metrics, the data model -- from the same inline diagrams and
stylesheet `render_report.py` uses for the full `index.html`. The output
pages are tracked, so a tracked README may link to them.

    .venv/Scripts/python.exe scripts/render_report_pages.py

Every number comes from a tracked file (`datasets/golden-v1.0.0/
metrics.json`, `coverage.json`) or names the decision that records it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Template

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.render_report import _inline_svg  # noqa: E402

OUT_DIR = ROOT / "docs" / "reports"
METRICS_PATH = ROOT / "datasets" / "golden-v1.0.0" / "metrics.json"
COVERAGE_PATH = ROOT / "datasets" / "golden-v1.0.0" / "coverage.json"

STYLE = """
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto;
padding: 0 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.5; }
h1 { border-bottom: 2px solid #2a5; padding-bottom: .3rem; } h2 { margin-top: 2.5rem; }
.lede { color: #444; font-size: 1.05rem; }
.diagram { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 1rem;
margin: 1rem 0; overflow-x: auto; } .diagram svg { max-width: 100%; height: auto; }
.example { background: #fff; border-left: 4px solid #6ca2ee; padding: .6rem .9rem;
margin: .8rem 0; font-size: .95rem; } .example b { color: #2c5fc9; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ccc; padding: .5rem .7rem; text-align: left;
vertical-align: top; }
th { background: #eee; } code { background: #eee; padding: 0 .25rem; border-radius:
3px; }
.meta { color: #888; font-size: .85rem; } nav a { margin-right: 1rem; }
"""

NAV = """<nav><a href="index.html">Full report</a> <a href="hero-run.html">Hero run</a>
<a href="safety.html">Safety</a> <a href="metrics.html">Metrics</a>
<a href="data-model.html">Data model</a></nav>"""

PAGE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{{ title }}</title>
<style>{{ style }}</style></head>
<body>
{{ nav }}
<h1>{{ title }}</h1>
{{ body }}
<p class="meta">Regenerated {{ generated_at }}. No external network resources.</p>
</body></html>
""")

HERO = """
<p class="lede">The one scenario the project exists for, and what happened when it was
run live through the browser.</p>

<h2>The flow</h2>
<p>A guest's cart is under the minimum order sum. The agent reads the cart through
Silpo's official MCP server, lists every validation the cart carries (not only the one
the app shows), computes the exact gap in code, proposes two or three products that
close it, waits for consent to one specific product, performs one guarded write, reads
the cart back independently and shows a receipt of what actually changed. Checkout and
payment stay the guest's own action.</p>
<div class="diagram">{{ sequence_svg }}</div>

<h2>The live run, 2026-09-10</h2>
<table>
<tr><th>Step</th><th>Observed</th></tr>
<tr><td>Cart at the read</td><td>productsTotal 605.62 ₴ against a 699 ₴ minimum; two
validations: <code>order.cost.min</code> (error) and
<code>order.payment_types.disabled</code> (info) — the second one the app renders on
no screen a guest can reach</td></tr>
<tr><td>Gap, computed in code</td><td>93.38 ₴ (699 − 605.62), threshold read from the
validation's own context</td></tr>
<tr><td>Candidates</td><td>three products priced from the product search: 46.99 × 2,
94.99 × 1, 31.99 × 3 — each with its consent hash shown before consent</td></tr>
<tr><td>Consent</td><td>the third candidate; the recorded consent's
<code>args_hash</code> equal to that candidate's, with a <code>state_hash</code> of
the cart and a five-minute expiry</td></tr>
<tr><td>Write and read-back</td><td>expected +95.97, read back +95.97, <b>verified,
blocker cleared</b></td></tr>
<tr><td>Spend</td><td>5,205 tokens, $0.0042 at the pinned prices, from the provider's
own usage block</td></tr>
<tr><td>Afterwards</td><td>the cart restored by script to 605.62 (the restore refuses
if the cart moved since the receipt)</td></tr>
</table>
<div class="example"><b>What the price says.</b> On earlier live rounds the cart charged
less than the search predicted (99.00 expected, 89.10 charged) because the cart applies
a per-product loyalty discount the search does not carry. The receipt shows the number
the cart returned, not the prediction — which is the whole reason for the
read-back.</div>

<h2>What the console shows a jury during the run</h2>
<p>Left: an append-only log of the graph nodes the stream reported, each tagged MCP,
LLM, DB or pure, and the session's spend beside the project ceiling. Middle: the guest
card, in Ukrainian. Right: the cart as the server returned it — one state at the read,
one per read-back, the added line marked. Four claims with their live evidence: the
server returns more than the app shows; money is computed by code, never by the model;
nothing is written without item-bound consent; success is never asserted, only read
back. Every metric shown carries its sample size and interval.</p>

<h2>The other scenarios</h2>
<table>
<tr><th>Scenario</th><th>Cart state</th><th>What it shows</th></tr>
<tr><td>Second round</td><td>the first write leaves a residual gap</td><td>a new
diagnosis and offer for the remainder; both receipts stay on screen</td></tr>
<tr><td>Compensation</td><td>a write produced an unwanted diff</td><td>an offer to
undo exactly that write, re-authorised by the guard, read back the same way</td></tr>
<tr><td>Safeguard</td><td>a lapsed delivery slot, out-of-stock lines</td><td>«причина
невідома»: no known rule applies, so no action is proposed — the system declining to
act blind</td></tr>
<tr><td>Logout</td><td>any</td><td>the credential is deleted; a fresh session answers
401 until the guest logs in again</td></tr>
</table>
"""

SAFETY = """
<p class="lede">What keeps a language model from touching a real cart on its own.</p>

<h2>The invariants</h2>
<ul>
<li><b>One write site.</b> Only the Write Guard node may call a write tool; a layering
test bans importing the write allowlist anywhere else.</li>
<li><b>The model never authorises.</b> It plans and explains; money, gap arithmetic and
post-conditions are pure code.</li>
<li><b>Consent is bound to one action and one cart state</b> — <code>action_id</code>,
canonical arguments, <code>args_hash</code>, <code>state_hash</code>, expiry. A generic
"yes" after the plan changed carries nothing forward.</li>
<li><b><code>success</code> from the server proves nothing.</b> Every write is followed
by an independent read-back; an unreachable read-back yields <code>unverified</code>,
never a successful receipt.</li>
<li><b>The tool list is untrusted input.</b> It is discovered live, hashed per tool, and
a new or changed tool is quarantined until reviewed — the live server ships imperative
instructions inside tool descriptions, and a planner that obeyed them would optimise
for the retailer's cheque, not the guest's.</li>
<li><b>The session is the ordinary web-session model.</b> An <code>HttpOnly; Secure;
SameSite=Lax</code> cookie, one credential per session, logout deletes it, idle tokens
expire after 30 minutes, and every route checks the cookie against the path.</li>
</ul>

<h2>Consent → guard → write → read-back</h2>
<div class="diagram">{{ g5_sequence_svg }}</div>

<h2>When the guard refuses</h2>
<p>Over twenty refusal branches, each with a test: an unknown or quarantined tool, a
schema hash that drifted, an expired or consumed consent, a hash that does not match
the cart as it is now, no budget reserve for the read-back. A refusal is terminal for
the ordinary path and the guest is told why, in Ukrainian.</p>
<div class="diagram">{{ g5_refusal_svg }}</div>

<h2>Undoing a change the guest did not want</h2>
<p>A verified write is not a recovered cart. When a write left an unwanted diff, the
guest is offered a compensation — a second, separately allowlisted tool, re-authorised
by the same guard and read back the same way.</p>
<div class="diagram">{{ g8_compensation_happy_svg }}</div>

<h2>Regression net</h2>
<table>
<tr><th>Row</th><th>Rubric</th><th>Status</th></tr>
{% for row in coverage %}
<tr><td>{{ row.rg_id }}</td><td>{{ row.rubric }}</td><td>{{ row.status }}</td></tr>
{% endfor %}
</table>
<p>A row reads <code>pass</code> only on a recorded run artefact that git tracks;
<code>blocked</code> names a structural reason (the budget loop's three dead
dimensions), <code>not_applicable</code> is the one row the brief itself defers
(RAG).</p>
"""

METRICS = """
<p class="lede">Eight numbers, each with the population it was measured over, its 95%
interval and its caveat — never a bare percentage.</p>

<table>
<tr><th>Metric</th><th>Value</th><th>n</th><th>95% Wilson</th><th>Caveat</th></tr>
{% for m in metrics %}
<tr><td><code>{{ m.name }}</code></td><td>{{ m.display }}</td><td>{{ m.n }}</td>
<td>{{ m.ci }}</td><td>{{ m.caveat }}</td></tr>
{% endfor %}
</table>
<p>Population <code>{{ population }}</code>: the 18 offline repeats over the tracked
recorded bundles, replayed through the same compiled graph the live path runs.
Regenerate with <code>{{ regenerate }}</code>; a gate test asserts the committed file
agrees with a fresh regeneration. Live repeats: 18 of 18 on 2026-09-09.</p>
<div class="diagram">{{ g9_metrics_svg }}</div>

<h2>How to read them</h2>
<p>The four 0.00/1.00 rows are unrefuted, not proven: at n = 33 a proportion of 1.00
still has a lower bound of 0.90. FalseRecovery is a count. SearchPriceFidelity is not a
success rate — it measures how often the search price equalled the price the cart
charged, and it is low because the cart applies a loyalty discount the search does not
see. DisclosureRate rests on one audited observation and is reported as one.</p>

<h2>Cost</h2>
<p>18 live runs on 2026-09-09 cost $0.13 in total at the pinned OpenRouter prices —
about
$0.007 per episode with both model calls; the console session of 2026-09-10 cost
$0.0042. Every usage figure comes from the provider's own usage block, never an
estimate. Project ceiling $20; spend to date under $1.</p>

<h2>Not measured</h2>
<p>Before/after figures from moderated guest sessions (n = 0 — no access to
participants; the protocol is written), and any conversion or revenue effect. Neither
is substituted by a proxy. The evaluation judges are validated as structural-defect
detectors, not as a measure of Ukrainian quality, so no judge score appears
anywhere.</p>
"""

DATA_MODEL = """
<p class="lede">Everything the service remembers, in six tables in Neon Postgres.</p>
<div class="diagram">{{ er_svg }}</div>
<table>
<tr><th>Table</th><th>One row is</th><th>Why it exists</th></tr>
<tr><td><code>sessions</code></td><td>one guest's visit</td><td>the thread the graph
checkpoints under; the owner hash the guard checks on every write</td></tr>
<tr><td><code>oauth_tokens</code></td><td>the one credential for that
visit</td><td>backend-only; logout deletes exactly this row; idle rows expire on
read</td></tr>
<tr><td><code>consents</code></td><td>one approved action</td><td>bound to the cart
state by two hashes and an expiry; consumed once</td></tr>
<tr><td><code>idempotency_keys</code></td><td>one claimed write</td><td>claimed
immediately before the call so a retry can never write twice</td></tr>
<tr><td><code>receipts</code></td><td>one write's outcome</td><td>before and after,
expected and actual, verified or unverified — the audit trail a logout must not
touch</td></tr>
<tr><td><code>schema_version</code></td><td>the applied migration</td><td>an
incompatible state version without a migration fails safe</td></tr>
</table>
<p>Consents and receipts reference a session without cascade, so a session row is never
deleted and the audit trail survives a logout. Nothing stores the guest's address or
coordinates as a column; the cart snapshots inside a receipt are reduced to amounts
before anything reaches a browser. The LangGraph checkpointer keeps the in-flight graph
state in its own tables, linked by a shared thread id and no foreign key.</p>
"""


def _metrics() -> Dict[str, Any]:
    doc = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = []
    for m in doc["metrics"]:
        if m["name"] == "DisclosureRate":
            display = "1 of 1"
        elif m["name"] == "FalseRecovery":
            display = "0" if m["value"] == 0 else str(m["value"])
        elif m["value"] is None:
            display = "N/A"
        else:
            display = f"{m['value']:.2f}"
        ci = (
            "—"
            if m["interval"] is None
            else f"[{m['interval'][0]:.2f}, {m['interval'][1]:.2f}]"
        )
        rows.append({**m, "display": display, "ci": ci})
    return {
        "metrics": rows,
        "population": doc["population"],
        "regenerate": doc["regenerate"],
    }


def render_all() -> List[Path]:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))["rows"]
    pages = {
        "hero-run.html": (
            "Lantern — the hero run",
            HERO,
            {"sequence_svg": _inline_svg("hero_sequence")},
        ),
        "safety.html": (
            "Lantern — safety by construction",
            SAFETY,
            {
                "g5_sequence_svg": _inline_svg("g5_consent_write_readback_sequence"),
                "g5_refusal_svg": _inline_svg("g5_guard_refusal_sequence"),
                "g8_compensation_happy_svg": _inline_svg(
                    "g8_compensation_happy_sequence"
                ),
                "coverage": coverage,
            },
        ),
        "metrics.html": (
            "Lantern — measured results",
            METRICS,
            {"g9_metrics_svg": _inline_svg("g9_metrics_results"), **_metrics()},
        ),
        "data-model.html": (
            "Lantern — data model",
            DATA_MODEL,
            {"er_svg": _inline_svg("neon_schema_er")},
        ),
    }
    written = []
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, (title, body, ctx) in pages.items():
        html = PAGE.render(
            title=title,
            style=STYLE,
            nav=NAV,
            body=Template(body).render(**ctx),
            generated_at=stamp,
        )
        out = OUT_DIR / name
        out.write_text(html, encoding="utf-8")
        written.append(out)
    return written


def main() -> int:
    for path in render_all():
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
