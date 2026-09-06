"""Render `docs/reports/index.html` — the one part of `docs/` published to
the public repository.

This page is deliberately NOT a stage-by-stage build log: no list of files
written, no decision or amendment ledger, no test-pass counts, no gate
names. Its only job is to show a reader who has never seen the internal
plan **how the system's components interact** (seven diagrams, inlined as
SVG so the page needs no network connection) and **why that interaction is
expected to produce a positive, measurable outcome for the guest and the
business**. Everything about how the project got here — decisions, plan
corrections, per-gate evidence — stays in `docs/` locally and is never read
by this script.

Diagram prose is kept at roughly CEFR B1: short sentences, common words, one
worked example per diagram. The diagrams themselves follow
`docs/diagram-conventions.md` (Arial 12/14, one five-colour layer system,
UML message and pseudostate conventions).

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
padding: 0 1rem; color: #1a1a1a; background: #fafafa; line-height: 1.5; } h1 {
border-bottom: 2px solid #2a5; padding-bottom: .3rem; } h2 { margin-top: 2.5rem; } h3
{ margin-top: 2rem; font-size: 1.05rem; } .lede { color: #444; font-size: 1.05rem; }
.diagram { background: white; border: 1px solid #ddd; border-radius: 6px; padding:
1rem; margin: 1rem 0; overflow-x: auto; } .diagram svg { max-width: 100%; height:
auto; } .example { background: #fff; border-left: 4px solid #6ca2ee; padding: .6rem
.9rem; margin: .8rem 0; font-size: .95rem; } .example b { color: #2c5fc9; } .palette {
border-collapse: collapse; margin: 1rem 0; } .palette td { border: 1px solid #ccc;
padding: .35rem .7rem; } .swatch { width: 22px; height: 14px; display: inline-block;
border: 1px solid #555; border-radius: 2px; vertical-align: middle; } table {
border-collapse: collapse; width: 100%; margin: 1rem 0; } th, td { border: 1px solid
#ccc; padding: .5rem .7rem; text-align: left; } th { background: #eee; } .pending {
color: #a55; font-style: italic; } .measured { color: #1a7a1a; font-weight: 600; }
.meta { color: #888; font-size: .85rem; }
</style></head>
<body>
<h1>Lantern — Checkout Transparency Agent for Silpo</h1>
<p class="lede">How the pieces interact, and why that interaction is expected to help
the guest and the business — not a record of how the project was built.</p>

<h2>How to read these diagrams</h2>
<p>All diagrams use one colour system. The colour of a block always shows which layer
of the system the block belongs to. The same colour means the same thing on every
diagram.</p>
<table class="palette">
<tr><td><span class="swatch" style="background:#fdf9db"></span> External</td>
<td>Systems outside our code: the guest, the Silpo MCP server, Neon, OpenRouter,
        LangSmith.</td></tr>
<tr><td><span class="swatch" style="background:#91ccf1"></span> Interface</td>
<td>What the guest or the developer touches: the API, the web app, local
    scripts.</td></tr>
<tr><td><span class="swatch" style="background:#6ca2ee"></span> Application</td>
    <td>The agent that decides the order of steps: the LangGraph state graph.</td></tr>
<tr><td><span class="swatch" style="background:#9a85e1"></span> Domain / Safety</td>
<td>Pure business rules and the write guard. This code does no network
    calls.</td></tr>
<tr><td><span class="swatch" style="background:#afa4de"></span> Infra / adapter</td>
<td>Code that talks to the outside world: the MCP adapter, the database
        checkpointer.</td></tr>
</table>

<h2>1. System architecture</h2>
<p>This diagram shows the main parts of the system and how a request moves through
them. The guest talks only to the interface. The interface starts the Recovery Agent.
The agent uses the Domain Core to compute numbers, and it must pass the Write Guard
before any change to the cart. Only the MCP Adapter talks to external services.</p>
<p>The important rule is visible in the shape: there is one road to a cart change, and
it goes through the Write Guard. The guest's browser can never reach the Silpo server
directly.</p>
<div class="example"><b>Example.</b> A guest opens a blocked cart and clicks "fix with
AI". The interface starts a session, the agent reads the cart, the Domain Core
computes that the cart is 194.11 UAH below the minimum order sum, and nothing is
changed yet — the write path stays closed until the guest agrees to one specific
action.</div>
<div class="diagram">{{ c4_svg }}</div>

<h2>2. Deployment</h2>
<p>This diagram shows where each part runs. Today the web app and the API run on the
developer machine. Four external services are used: Neon Postgres keeps all state,
LangSmith receives traces, OpenRouter serves the language model, and the Silpo MCP
server provides the cart data. The public tier on Render is drawn with dashed lines
because it is optional and not deployed yet.</p>
<p>No state is kept on the service disk. If the process restarts, the session
continues from the database.</p>
<div class="example"><b>Example.</b> The demo runs fully on a laptop. If the laptop
process stops in the middle of a recovery, the same session can continue later,
because the consent record and the graph checkpoint are already in Neon, not in
memory.</div>
<div class="diagram">{{ deployment_svg }}</div>

<h2>3. The hero recovery flow</h2>
<p>This diagram shows the order of messages in one recovery. Time goes from top to
bottom. The agent first reads the live cart through the MCP adapter. Then it sends a
diagnosis and two or three options to the guest. The guest chooses one option. Only
after that the agent performs one write, and then reads the cart again to check the
result.</p>
<p>The last step matters most: the system never trusts the answer of the write call.
It proves the result with a second, independent read.</p>
<div class="example"><b>Example.</b> The guest agrees to add one item for 39.99 UAH.
The agent writes once, then reads the cart again. The products total grew by exactly
39.99, so the receipt is honest. If the second read had failed, the result would be
reported as "unverified", not as success.</div>
<div class="diagram">{{ sequence_svg }}</div>

<h2>4. Safety state machine</h2>
<p>This diagram shows every state of the agent and every way to move between them.
There is exactly one path that ends with a receipt. All other paths end in an honest
non-success.</p>
<p>Three safety points are visible. The agent stops at <i>Consent</i> and waits for
the guest. It re-reads the cart before writing, and returns to planning if the cart
changed in the meantime. After the write it can only reach <i>Receipt</i> if the
read-back matches; otherwise it ends in <i>Unverified</i>.</p>
<div class="example"><b>Example.</b> The guest waits five minutes before confirming.
In that time another device adds an item to the same cart. The re-read sees a
different cart state, so the agent does not write. It goes back to planning and offers
a fresh option based on the new cart.</div>
<div class="diagram">{{ state_svg }}</div>

<h2>5. LangGraph structure</h2>
<p>The agent is built with LangGraph. This diagram shows the standard parts of such an
application, without project details. A typed <i>State</i> object describes the data.
The <i>StateGraph</i> collects nodes and edges and compiles them into an executable
graph. At run time a node reads the state and returns an update, and a router decides
the next node.</p>
<p>The checkpointer saves the state after every step. This is what makes it possible
to stop the graph, wait for a human answer, and continue later in a different
process.</p>
<div class="example"><b>Example.</b> The graph reaches the consent step and stops. The
state is saved to Neon. Two minutes later the guest answers, the graph is loaded from
the checkpoint, and it continues from the same point instead of starting again.</div>
<div class="diagram">{{ langgraph_svg }}</div>

<h2>6. MCP Adapter components</h2>
<p>This diagram shows the modules inside the MCP adapter. <code>client.py</code> keeps
the tool registry, <code>auth.py</code> keeps the OAuth token, <code>errors.py</code>
converts protocol errors into typed errors, and <code>sanitizer.py</code> removes
personal data from captured test files. The MCP server is treated as untrusted
input.</p>
<p>The <code>redaction.py</code> module is important for privacy: an error from the
server is reduced to a code and a checked message before it can reach a trace.</p>
<div class="example"><b>Example.</b> The server returns an error with a long free-text
field. The adapter keeps only the error code and a cleaned message. The free-text
field is dropped, so it can never appear in an external trace.</div>
<div class="diagram">{{ mcp_adapter_svg }}</div>

<h2>7. Tool registry and schema drift</h2>
<p>The list of server tools is not fixed in the code. The agent asks the registry, and
the registry asks the server when its cache is old. The registry also compares the new
tool names with the last snapshot and marks any name it has not seen before.</p>
<p>This protects the system from silent change. A new tool never becomes usable only
because it appeared in the server's answer.</p>
<div class="example"><b>Example.</b> The server adds a new write tool between two
runs. The registry marks it as unknown. The Write Guard still allows only the reviewed
tools, so the new tool cannot be called until a person reviews it.</div>
<div class="diagram">{{ tools_list_svg }}</div>

<h2>8. Why this is expected to help, not just work</h2>
<p>The mechanism above targets a specific, observed gap: the retailer's own MCP server
already returns more structured detail about why a cart is blocked than the shopping
app's screen displays. A cart can carry two independent blocking conditions and the
guest is shown only one message for either of them. Lantern's diagnosis step surfaces
every condition the cart already reports — including the ones the screen never renders
— before proposing any change, and never authorizes a write the guest has not seen and
approved in those exact terms.</p>
<p>The business argument follows the same shape: a cart that reaches checkout is worth
more to the retailer than one abandoned at a blocker, and a guest who understood why
their cart was blocked and fixed it in one step spent less time and fewer actions
doing it than one navigating a generic "add more items" prompt with no further
detail.</p>

<h2>9. Measured outcome</h2>
{% if metrics %}
<table>
<tr><th>Metric</th><th>Value</th><th>n</th></tr>
{% for m in metrics %}
<tr><td>{{ m.name }}</td><td class="measured">{{ m.value }}</td><td>{{ m.n }}</td></tr>
{% endfor %}
</table>
{% else %}
<p class="pending">Not yet measured. This section will report recovery completion
rate, median time-to-recovery versus the app, and disclosure rate — each with its
sample size, never as a bare percentage — once moderated before/after testing produces
them.</p>
{% endif %}

<p class="meta">Regenerated {{ generated_at }}. No external network resources.</p>
</body></html>
""")


def _inline_svg(name: str) -> str:
    """Inline one exported diagram.

    The exported `.svg` files are standalone XML documents, so they start with
    an `<?xml ... ?>` prolog. That prolog is invalid inside an HTML body — it
    stops the SVG from rendering and can surface as stray text — so it is
    stripped here rather than omitted from the export, which still needs to be
    a well-formed standalone file.
    """
    path = UML_SVG_DIR / f"{name}.svg"
    if not path.exists():
        return f"<p><em>Diagram not available locally: {name}.svg</em></p>"
    markup = path.read_text(encoding="utf-8")
    return markup[markup.index("<svg") :] if "<svg" in markup else markup


def _load_metrics() -> list[dict] | None:
    if not METRICS_PATH.exists():
        return None
    data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    return data.get("metrics") or None


def render() -> Path:
    html = TEMPLATE.render(
        c4_svg=_inline_svg("c4_container"),
        deployment_svg=_inline_svg("deployment"),
        sequence_svg=_inline_svg("hero_sequence"),
        state_svg=_inline_svg("graph_state"),
        langgraph_svg=_inline_svg("langgraph_structure"),
        mcp_adapter_svg=_inline_svg("mcp_adapter_component"),
        tools_list_svg=_inline_svg("tools_list_sequence"),
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
