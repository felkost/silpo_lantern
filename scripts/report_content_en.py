"""English page bodies for the documentation site. Kept apart from the
renderer so the two languages can be compared file against file, and so
`tests/unit/test_report_site_is_bilingual.py` can assert that every
section anchor and every diagram slot exists in both.
"""

LABELS = {
    "lang_name": "English",
    "other_lang_name": "Українська",
    "brand": "Lantern docs",
    "on_this_page": "On this page:",
    "regenerated": "Regenerated",
    "no_network": "No external network resources.",
    "groups": {"Overview": "Overview", "Evidence": "Evidence"},
}

NAV = [
    ("index.html", "Start here", "Overview"),
    ("architecture.html", "Architecture", "Overview"),
    ("recovery.html", "Hero recovery", "Evidence"),
    ("safety.html", "Safety & consent", "Evidence"),
    ("evidence.html", "Measurements", "Evidence"),
    ("data-model.html", "Data model", "Evidence"),
]

TITLES = {
    "index.html": (
        "Technical documentation",
        "Make a blocked checkout understandable — and safely actionable",
    ),
    "architecture.html": ("Overview", "Architecture"),
    "recovery.html": ("Evidence", "Hero recovery"),
    "safety.html": ("Evidence", "Safety & consent"),
    "evidence.html": ("Evidence", "Measurements"),
    "data-model.html": ("Evidence", "Data model"),
}

SECTIONS = {
    "index.html": [
        ("route", "Reading route"),
        ("claim", "Design claim"),
        ("how", "One line"),
    ],
    "architecture.html": [
        ("containers", "Containers"),
        ("layers", "Layers"),
        ("rules", "The 13 domain rules"),
        ("graph", "The graph"),
        ("deployment", "Deployment"),
        ("mcp", "MCP adapter"),
        ("domain", "Domain core"),
        ("planner", "Planner and ranking"),
    ],
    "recovery.html": [
        ("flow", "The flow"),
        ("live", "The live run"),
        ("states", "State machine"),
        ("console", "The console"),
        ("scenarios", "Other scenarios"),
    ],
    "safety.html": [
        ("guard", "What the Write Guard is"),
        ("invariants", "Invariants"),
        ("consent", "Consent → read-back"),
        ("refusal", "Refusal"),
        ("compensation", "Compensation"),
        ("rg", "Regression net"),
    ],
    "evidence.html": [
        ("metrics", "Metrics"),
        ("reading", "How to read them"),
        ("cost", "Cost"),
        ("economics", "Unit economics"),
        ("unmeasured", "Not measured"),
    ],
    "data-model.html": [
        ("tables", "Tables"),
        ("choices", "Two choices"),
        ("checkpointer", "Checkpointer"),
    ],
}

INDEX = """
<p class="lede">Lantern reads a Silpo cart through the official MCP server, explains its
validations — including the ones the app's own screen never renders — computes the
shortfall by arithmetic rather than by asking the language model, proposes a minimal
option, and changes the cart only after explicit, item-bound consent. A separate
read-back proves the result.</p>
<div class="notice"><strong>Scope.</strong> The MVP covers one recovery path, the
minimum-order-sum blocker, plus a read-only delivery-channel comparison. Checkout and
payment always remain the guest's own action. Live at
<code>https://silpo-lantern.onrender.com/</code>.</div>

<h2 id="route">Read this documentation in five steps</h2>
<div class="grid">
<article class="card"><h3>1. Architecture</h3><p>The system boundary: one FastAPI
service with the React console, the LangGraph workflow, the MCP adapter, Neon Postgres
— and the one road to a cart change.</p>
<a href="architecture.html">Understand the system →</a></article>
<article class="card"><h3>2. Hero recovery</h3><p>The one end-to-end scenario, and
what happened when it ran live through the browser: diagnosis, options, consent,
guarded write, receipt.</p><a href="recovery.html">Follow the run →</a></article>
<article class="card"><h3>3. Safety &amp; consent</h3><p>The invariants: one write
site, a model that never authorises, binding hashes, expiry, independent verification,
quarantine of tool drift.</p><a href="safety.html">Review the safeguards →</a></article>
<article class="card"><h3>4. Measurements</h3><p>Eight metrics with their populations,
95% intervals and caveats; the cost of an episode; what was deliberately not
measured.</p><a href="evidence.html">Inspect the evidence →</a></article>
<article class="card"><h3>5. Data model</h3><p>The six persisted tables — sessions,
consent, idempotency, receipts, tokens — and the checkpointer beside them.</p>
<a href="data-model.html">Inspect the storage →</a></article>
</div>

<h2 id="claim">The design claim</h2>
<p>A tool's <code>success</code> flag is not proof. The system distinguishes <em>"the
agreed write occurred"</em> from <em>"the cart is now eligible for checkout"</em>, and
both require evidence from a fresh read of the cart. Everything else on these pages —
the single write site, the hash-bound consent, the quarantine of tool drift, the metrics
with their intervals — exists to make that claim checkable rather than believable.</p>

<h2 id="how">How the recovery works, in one line</h2>
<p><code>blocked cart → diagnosis → concrete options → consent → minimal change →
read-back receipt</code></p>
"""

ARCHITECTURE = """
<p class="lede">The main parts of the system and how a request moves through them. The
important rule is visible in the shape: there is one road to a cart change, and it goes
through the Write Guard.</p>

<h2 id="containers">Containers</h2>
<p>The guest talks only to the web page. It starts the Recovery Agent, a LangGraph
graph. The agent uses the Domain Core to compute every number, and it must
pass the <b>Write Guard</b> before any change to the cart: the single node in the whole
system that is allowed to call a write tool, and which checks the consent, the cart and
the tool's own schema before it authorises one. It is described in full on the
<a href="safety.html#guard">safety page</a>. Only the <b>MCP Adapter</b> — labelled
that way on the diagram below — talks to Silpo: MCP is the open protocol through which
Silpo exposes the cart to applications, and the adapter is this project's single module
that speaks it. The guest's browser can never reach the Silpo server directly.</p>
<div class="example"><b>Example.</b> A guest opens a blocked cart and starts a session.
The agent reads the cart, the Domain Core computes that it is 93.38 ₴ below the minimum
order sum, and nothing is changed yet — the write path stays closed until the guest
agrees to one specific action.</div>
<div class="diagram">{{ c4_svg }}</div>

<h2 id="layers">Layers and what each may do</h2>
<table>
<tr><th>Layer</th><th>Contents</th><th>Rule</th></tr>
<tr><td>Domain</td><td>cart, validation, diagnosis and receipt models; the 13 domain
rules below; gap arithmetic; evidence gate; ranking</td><td>no I/O — testable without a
network</td></tr>
<tr><td>Safety</td><td>the Write Guard: allowlist, consent binding, hashes, per-tool
schema hash, budget reserve, read-back gate</td><td>the only place a write tool is
called</td></tr>
<tr><td>Infra (the MCP adapter)</td><td>MCP client and OAuth, dynamic tool registry
with quarantine, Neon
repository and checkpointer, tracing with redaction</td><td>talks to the outside;
trusts nothing it receives</td></tr>
<tr><td>Application</td><td>the LangGraph graph and prompts</td><td>the model plans and
explains, never authorises</td></tr>
<tr><td>Interface</td><td>FastAPI routes, the React guest card and the jury
console</td><td>Ukrainian for the guest; English identifiers for the observer</td></tr>
</table>
<p>Layer membership is enforced by a test that walks every import, not by directory
nesting alone.</p>

<h2 id="rules">The 13 domain rules</h2>
<p>The project applies thirteen domain rules — about money, time and evidence. Each
one exists as its own test file named after the rule
(<code>tests/unit/test_dr_01…13</code>), so "does the rule hold" is a question the test
suite answers rather than a claim in a document. None of them needs a network to
run.</p>
<table>
<tr><th>#</th><th>Rule</th><th>Why it is not obvious</th></tr>
<tr><td>DR-01</td><td>Money is <code>Decimal</code>, coordinates are floats, quantity
keeps its fractional meaning</td><td>the cart returns coordinates as strings, which a
sibling tool rejects if passed on unconverted</td></tr>
<tr><td>DR-02</td><td>Time is UTC inside, Kyiv time on screen</td><td>a delivery slot
of 06:30 UTC is 09:30 for the guest</td></tr>
<tr><td>DR-03</td><td>The shortfall is <code>minOrderCost − productsTotal</code></td>
<td>comparing against the cart's grand total instead would invent a block on every
cart that carries a delivery fee or bonuses</td></tr>
<tr><td>DR-04</td><td>A surcharge is named "service fee" only where a confirmed one
exists; otherwise it is called a difference</td><td>naming an unknown amount invents a
fact</td></tr>
<tr><td>DR-05</td><td><code>deliveryCost: null</code> means "not applicable", never
zero</td><td>zero would read as free delivery</td></tr>
<tr><td>DR-06</td><td>An unregistered validation code is flagged, never treated as a
similar known one</td><td>two live codes with no registry match were found in the very
first field session</td></tr>
<tr><td>DR-07</td><td>"Product no longer sold" outranks "not enough in stock" for the
same product</td><td>otherwise the guest is told to reduce a quantity of something that
cannot be bought at all</td></tr>
<tr><td>DR-08</td><td>A price of 0 is not automatically free or unavailable</td><td>
without proof of suitability such a line is not a candidate</td></tr>
<tr><td>DR-09</td><td>Totals and the shortfall are computed, never supplied by the
model</td><td>enforced by the functions' own signatures: there is no parameter through
which a total could arrive</td></tr>
<tr><td>DR-10</td><td>An incomplete evidence tuple cannot be represented</td><td>
product, price, availability, source tool and capture time are all required, so a
candidate without a verified price cannot exist</td></tr>
<tr><td>DR-11</td><td>The before/after difference is canonical and self-checking</td>
<td>a difference that would understate the real change raises instead of reporting</td>
</tr>
<tr><td>DR-12</td><td>Re-read before the write, read back immediately after</td><td>
the server's own write response carries no totals and no validations, so its
<code>success</code> cannot answer whether the block cleared</td></tr>
<tr><td>DR-13</td><td>Checkout, payment and age confirmation stay the guest's
own</td><td>a list in code, not a sentence in a comment, so a test can check it</td>
</tr>
</table>

<h2 id="graph">The graph</h2>
<p>Read → diagnose → compare channels → plan → collect and gate → rank → explain →
<em>wait for consent</em> → write guard → write and read-back → persist receipt. The
graph stops at consent and the state is saved to Neon; when the guest answers, it is
loaded from the checkpoint and continues from the same point, in any process.</p>
<p>The diagram below is the standard shape of a LangGraph application, without project
detail: a typed state feeds a builder that compiles to an executable graph, a
conditional edge routes each step, and a checkpointer persists the state after every
node — which is what makes stopping for a human answer possible at all. This project's
own node topology, exported from the code, is on the
<a href="safety.html#compensation">safety page</a>.</p>
<div class="diagram">{{ langgraph_svg }}</div>

<h2 id="deployment">Deployment</h2>
<p>On the developer machine the web app and the API are two processes. On the public
tier (Render, Frankfurt) they are one service: the API builds the web app at deploy time
and serves it from the root URL. Four external services: Neon Postgres keeps all state,
LangSmith receives traces, OpenRouter serves the language model, and the Silpo MCP
server provides the cart. No state is kept on the service disk.</p>
<div class="diagram">{{ deployment_svg }}</div>

<h2 id="mcp">The MCP adapter and the tool list</h2>
<p>Silpo's server offers what it can do as a list of <i>tools</i>: read the cart, search
products, change the cart. That list is discovered live through
<code>tools/list</code>, cached with an
expiry, hashed per tool, and a tool that is new or whose schema changed is quarantined
until reviewed. The live server ships imperative instructions inside tool descriptions;
the planner never sees them raw.</p>
<div class="diagram">{{ mcp_adapter_svg }}</div>
<p>And the registry's own sequence: the agent asks for the tool list, a stale cache is
refetched through the SDK, an oversized response is rejected before it is parsed, the
names are diffed against the previous snapshot, and only then are the tools handed
on.</p>
<div class="diagram">{{ tools_list_svg }}</div>

<h2 id="domain">The domain core</h2>
<p>The plain data objects that carry one recovery from a raw cart to a receipt. A cart
holds validations; each one that blocks checkout wraps into a blocker. The domain core
reads a cart and produces a diagnosis: an exact gap in money, never a guess. That
diagnosis later feeds a proposal with real evidence, and a consent record that only the
guarded write step may use. None of these objects call the network — every rule about
them is tested without a live server.</p>
<div class="diagram">{{ domain_class_svg }}</div>
<p>What happens to one cart as it moves through the core: a cart that does not match the
expected shape stops early with a named error; a cart that resolves cleanly moves on to
its gap; the rare case with no threshold at all is still shown, marked unverified rather
than given a confident number. Every path that reaches the end shows every validation
the cart carries, including the ones the app's own screen never displays.</p>
<div class="diagram">{{ domain_activity_svg }}</div>

<h2 id="planner">Planner, evidence gate, ranking</h2>
<p>After the diagnosis the planner proposes search terms — never a price or a product
id, which are structurally absent from what it may return. Every candidate the search
turns up is checked against the same call's own typed response before it can reach the
guest; one with no verified price, or marked unavailable, is dropped. What survives
is ranked by the smallest top-up that clears the gap.</p>
<div class="diagram">{{ g4_activity_svg }}</div>
<p>Drawn from a captured run against a live cart, not from the design: the two points
where a model is involved — proposing search terms, narrating one accepted candidate —
and what each may see. The planner receives a tool's name and JSON Schema, never its raw
description text; the product name reaching the narration step is wrapped as inert
data.</p>
<div class="diagram">{{ g4_sequence_svg }}</div>
"""

RECOVERY = """
<p class="lede">The one scenario the project exists for, and what happened when it was
run live through the browser.</p>

<h2 id="flow">The flow</h2>
<p>A guest's cart is under the minimum order sum. The agent reads the cart, lists every
validation it carries (not only the one the app shows), subtracts the cart's total from
the threshold the validation itself names, proposes two or three products that close the
difference, waits for consent to one specific product, performs one guarded write, reads
the cart back independently and shows a receipt of what actually changed.</p>
<div class="diagram">{{ sequence_svg }}</div>

<h2 id="live">The live run, 2026-09-10</h2>
<table>
<tr><th>Step</th><th>Observed</th></tr>
<tr><td>Cart at the read</td><td>productsTotal 605.62 ₴ against a 699 ₴ minimum; two
validations: <code>order.cost.min</code> (error) and
<code>order.payment_types.disabled</code> (info) — the second one the app renders on no
screen a guest can reach</td></tr>
<tr><td>Gap</td><td>93.38 ₴ — the subtraction 699 − 605.62, with the 699 taken from the
validation's own context, not from the model</td></tr>
<tr><td>Candidates</td><td>three products priced from the product search: 46.99 × 2,
94.99 × 1, 31.99 × 3 — each with its consent hash shown before consent</td></tr>
<tr><td>Consent</td><td>the third candidate; the recorded consent's
<code>args_hash</code> equal to that candidate's, with a <code>state_hash</code> of the
cart and a five-minute expiry</td></tr>
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

<h2 id="states">The state machine behind it</h2>
<p>Exactly one path ends with a receipt; every other path ends in an honest
non-success. The agent stops at consent and waits; it re-reads the cart before writing
and returns to planning if the cart changed; after the write it reaches
<em>Receipt</em> only if the read-back matches, otherwise <em>Unverified</em>.</p>
<div class="diagram">{{ state_svg }}</div>

<h2 id="console">What the console shows during the run</h2>
<p>Left: an append-only log of the graph nodes the stream reported — MCP, LLM, DB or
pure — and the session's spend beside the project ceiling. Middle: the guest card, in
Ukrainian. Right: the cart as the server returned it, one state at the read and one per
read-back, the added line marked. Four claims with their live evidence: the server
returns more than the app shows; money is arithmetic, never a model's answer; nothing
is written without item-bound consent; success is never asserted, only read back.</p>

<h2 id="scenarios">The other scenarios</h2>
<table>
<tr><th>Scenario</th><th>Cart state</th><th>What it shows</th></tr>
<tr><td>Second round</td><td>the first write leaves a residual gap</td><td>a new
diagnosis and offer for the remainder; both receipts stay on screen</td></tr>
<tr><td>Compensation</td><td>a write produced an unwanted diff</td><td>an offer to undo
exactly that write, re-authorised by the guard, read back the same way</td></tr>
<tr><td>Safeguard</td><td>a lapsed delivery slot, out-of-stock lines</td><td>«причина
невідома»: no known rule applies, so no action is proposed — the system declining to
act blind</td></tr>
<tr><td>Logout</td><td>any</td><td>the credential is deleted; a fresh session answers
401 until the guest logs in again</td></tr>
</table>
"""

SAFETY = """
<p class="lede">What keeps a language model from touching a real cart on its own.</p>

<h2 id="guard">What the Write Guard is</h2>
<p>One node in the graph, and the only place in the whole system from which a write tool
can be called. This is not a convention: no other module may even import the list of
allowed write tools, and a test that walks every import fails the build if one
tries.</p>
<p>Before any write it answers one question — may this exact change happen right now? —
and returns either an authorisation or a refusal with its reason. There are 22 ways to
refuse:</p>
<table>
<tr><th>It checks</th><th>And refuses when</th></tr>
<tr><td>The tool</td><td>it is not on the allowlist for this kind of action, it is a
guest-only action (checkout, payment, age confirmation), or it is quarantined</td></tr>
<tr><td>The tool's schema</td><td>the hash of the schema the server returns now differs
from the reviewed one — the server changed its interface mid-session</td></tr>
<tr><td>The consent</td><td>it expired, it was already used, or it belongs to a
different action, owner or session</td></tr>
<tr><td>The cart</td><td>the cart re-read a moment before the write no longer matches
the one the guest agreed about — someone changed it in another tab</td></tr>
<tr><td>The arguments</td><td>their fingerprint differs from the one recorded with the
consent; neither fingerprint is ever accepted from the browser, both are recomputed on
the server</td></tr>
<tr><td>The budget</td><td>there is not enough reserve left to read the cart back —
writing without being able to prove the outcome is not allowed</td></tr>
<tr><td>An undo</td><td>eight further checks that a compensation undoes exactly the
change this system itself made, as its receipt records it</td></tr>
</table>
<p>The language model never reaches this point: it proposes and explains, the guard is
handed only typed data, and the raw write tool is never shown to the model at all.</p>

<h2 id="invariants">The invariants</h2>
<ul>
<li><b>One write site.</b> Only the Write Guard node may call a write tool; a layering
test bans importing the write allowlist anywhere else.</li>
<li><b>The model never authorises.</b> It plans and explains; money, gap arithmetic and
post-conditions are ordinary deterministic code.</li>
<li><b>Consent is bound to one action and one cart state</b> — <code>action_id</code>,
canonical arguments, <code>args_hash</code>, <code>state_hash</code>, expiry. A generic
"yes" after the plan changed carries nothing forward.</li>
<li><b><code>success</code> from the server proves nothing.</b> Every write is followed
by an independent read-back; an unreachable read-back yields <code>unverified</code>,
never a successful receipt.</li>
<li><b>The tool list is untrusted input.</b> Discovered live, hashed per tool; a new or
changed tool is quarantined until reviewed.</li>
<li><b>The session is the ordinary web-session model.</b> An <code>HttpOnly; Secure;
SameSite=Lax</code> cookie, one credential per session, logout deletes it, idle tokens
expire after 30 minutes, and every route checks the cookie against the path.</li>
</ul>

<h2 id="consent">Consent → guard → write → read-back</h2>
<p>One consented action, end to end: the client posts only an action id, the server
recomputes both hashes from what it already holds, the graph resumes at the guard, the
cart is re-read, one write tool is called, the cart is read back independently, and the
receipt records the difference between what was expected and what the cart returned.</p>
<div class="diagram">{{ g5_sequence_svg }}</div>
<p>The only path that can change a cart, as a state machine. The graph stops and waits;
when consent arrives the guard authorises or refuses, and a refusal ends the run with no
cart touched. If the write is made, a separate read decides whether the result is a
receipt or the dashed state that records "we could not confirm this". A system that can
only report success will report success when it is wrong; this one has somewhere honest
to land.</p>
<div class="diagram">{{ write_state_svg }}</div>

<h2 id="refusal">When the guard refuses</h2>
<p>A refusal is terminal for the ordinary path, and the guest is told which of the
reasons above it was, in plain Ukrainian rather than in the wording of the code.</p>
<div class="diagram">{{ g5_refusal_svg }}</div>

<h2 id="compensation">Undoing a change the guest did not want</h2>
<p>A verified write is not a recovered cart. When a write left an unwanted diff, the
guest is offered a compensation — a second, separately allowlisted tool, re-authorised
by the same guard and read back the same way.</p>
<div class="diagram">{{ g8_compensation_happy_svg }}</div>
<p>The undo is refused whenever the system cannot prove what it would be undoing: the
re-read did not complete, the cart changed for another reason, or the change being
undone cannot be derived from what was recorded. Each refusal names which of those it
was.</p>
<div class="diagram">{{ g8_compensation_refusal_svg }}</div>
<p>The complete route a session can take, with the undo shown as what it is: a second
pass through the same approval point, never a shortcut around it.</p>
<div class="diagram">{{ g8_topology_svg }}</div>

<h2 id="rg">Regression net</h2>
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

EVIDENCE = """
<p class="lede">Eight numbers, each with the population it was measured over, its 95%
interval and its caveat — never a bare percentage.</p>

<h2 id="metrics">The metrics</h2>
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

<h2 id="reading">How to read them</h2>
<p>The four 0.00/1.00 rows are unrefuted, not proven: at n = 33 a proportion of 1.00
still has a lower bound of 0.90. FalseRecovery is a count. SearchPriceFidelity is not a
success rate — it measures how often the search price equalled the price the cart
charged, and it is low because the cart applies a loyalty discount the search does not
see. DisclosureRate rests on one audited observation and is reported as one.</p>

<h2 id="cost">Cost</h2>
<p>18 live runs on 2026-09-09 cost $0.13 in total at the pinned OpenRouter prices —
about $0.007 per episode with both model calls; the console session of 2026-09-10 cost
$0.0042. Every usage figure comes from the provider's own usage block, never an
estimate. Project ceiling $20; spend to date under $1.</p>

<h2 id="economics">Unit economics</h2>
<p>Stated as the plan's formula with variables, not a projection:
<code>Vnet = B × (p₁ × M₁ − p₀ × M₀ − c) + ΔS × C − F</code>. B — recovery-eligible
episodes; p₁/p₀ — completed purchases with and without the agent; M₁/M₀ — marginal
contribution per purchase; c — the agent's variable cost per episode; ΔS — support
contacts avoided; C — cost of one; F — fixed integration cost. Only c is measured. At
c ≈ $0.01 the agent pays for itself if one recovered purchase in a hundred episodes
carries more than one dollar of margin — provided p₁ − p₀ &gt; 0, which is what an A/B
pilot over eligible episodes would establish.</p>

<h2 id="unmeasured">Not measured</h2>
<p>Before/after figures from moderated guest sessions (n = 0 — no access to
participants; the protocol is written), and any conversion or revenue effect. Neither
is substituted by a proxy. The evaluation judges are validated as structural-defect
detectors, not as a measure of Ukrainian quality, so no judge score appears
anywhere.</p>
"""

DATA_MODEL = """
<p class="lede">Everything the service remembers, in six tables in Neon Postgres.</p>
<div class="diagram">{{ er_svg }}</div>

<h2 id="tables">The tables</h2>
<table>
<tr><th>Table</th><th>One row is</th><th>Why it exists</th></tr>
<tr><td><code>sessions</code></td><td>one guest's visit</td><td>the thread the graph
checkpoints under; the owner hash the guard checks on every write</td></tr>
<tr><td><code>oauth_tokens</code></td><td>the one credential for that visit</td>
<td>backend-only; logout deletes exactly this row; idle rows expire on read</td></tr>
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

<h2 id="choices">Two choices visible in the shape</h2>
<p>Consents and receipts reference a session <em>without</em> cascade, so a session row
is never deleted and the audit trail survives a logout. Nothing stores the guest's
address or coordinates as a column; the cart snapshots inside a receipt are reduced to
amounts before anything reaches a browser.</p>

<h2 id="checkpointer">The checkpointer beside it</h2>
<p>LangGraph keeps the in-flight graph state in its own four tables, in the same
database, keyed by the session's thread id — no foreign key in either direction, because
the library owns its migrations and the application owns its rows.</p>
"""

BODIES = {
    "index.html": INDEX,
    "architecture.html": ARCHITECTURE,
    "recovery.html": RECOVERY,
    "safety.html": SAFETY,
    "evidence.html": EVIDENCE,
    "data-model.html": DATA_MODEL,
}
