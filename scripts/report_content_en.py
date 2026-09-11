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
        ("graph", "Processing one request"),
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
payment always remain the Customer's own action. Live at
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
<p>The Customer talks only to the web page. It starts the Recovery Agent, a LangGraph
graph. The agent uses the Domain Core to compute every number, and it must
pass the <b>Write Guard</b> before any change to the cart: the single node in the whole
system that is allowed to call a write tool, and which checks the consent, the cart and
the tool's own schema before it authorises one. It is described in full on the
<a href="safety.html#guard">safety page</a>. Only the <b>MCP Adapter</b> — labelled
that way on the diagram below — talks to Silpo: MCP is the open protocol through which
Silpo exposes the cart to applications, and the adapter is this project's single module
that speaks it. The Customer's browser can never reach the Silpo server directly.</p>
<div class="example"><b>Example.</b> A Customer opens a blocked cart and starts a
session. The agent reads the cart, the Domain Core computes that it is 93.38 ₴ below
the minimum
order sum, and nothing is changed yet — the write path stays closed until the Customer
agrees to one specific action.</div>
<p class="meta">The diagrams label the person <code>Guest</code> — Silpo's own term for
a signed-in shopper; these pages call them the Customer.</p>
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
<tr><td>Interface</td><td>FastAPI routes, the React Customer card and the jury
console</td><td>Ukrainian for the Customer; English identifiers for the
observer</td></tr>
</table>
<p>Layer membership is enforced by a test that walks every import, not by directory
nesting alone.</p>

<h2 id="rules">The 13 domain rules</h2>
<p>The project applies thirteen domain rules — about money, time and evidence. Each
one exists as its own test file named after the rule
(<code>tests/unit/test_dr_01…13</code>), so "does the rule hold" is a question the test
suite answers rather than a claim in a document. None of them needs a network to
run. The five in <b>bold</b> are the product promise itself: the figure the client is
shown, who may compute it, no offer without verified price and availability, proof by
reading the cart back, and the boundary of what the agent never does.</p>
<table>
<tr><th>#</th><th>Rule</th><th>Why it is not obvious</th></tr>
<tr><td>01</td><td>Money is <code>Decimal</code>, coordinates are floats, quantity
keeps its fractional meaning</td><td>the cart returns coordinates as strings, which a
sibling tool rejects if passed on unconverted</td></tr>
<tr><td>02</td><td>Time is UTC inside, Kyiv time on screen</td><td>a delivery slot
of 06:30 UTC is 09:30 for the Customer</td></tr>
<tr><td>03</td><td><b>The shortfall is <code>minOrderCost − productsTotal</code></td>
<td>comparing against the cart's grand total instead would invent a block on every
cart that carries a delivery fee or bonuses</td></tr>
<tr><td>04</b></td><td>A surcharge is named "service fee" only where a confirmed one
exists; otherwise it is called a difference</td><td>naming an unknown amount invents a
fact</td></tr>
<tr><td>05</td><td><code>deliveryCost: null</code> means "not applicable", never
zero</td><td>zero would read as free delivery</td></tr>
<tr><td>06</td><td>An unregistered validation code is flagged, never treated as a
similar known one</td><td>two live codes with no registry match were found in the very
first field session</td></tr>
<tr><td>07</td><td>"Product no longer sold" outranks "not enough in stock" for the
same product</td><td>otherwise the Customer is told to reduce a quantity of something
that
cannot be bought at all</td></tr>
<tr><td>08</td><td>A price of 0 is not automatically free or unavailable</td><td>
without proof of suitability such a line is not a candidate</td></tr>
<tr><td>09</td><td><b>Totals and the shortfall are computed, never supplied by the
model</b></td><td>enforced by the functions' own signatures: there is no parameter
through
which a total could arrive</td></tr>
<tr><td>10</td><td><b>An incomplete evidence tuple cannot be represented</b></td><td>
product, price, availability, source tool and capture time are all required, so a
candidate without a verified price cannot exist</td></tr>
<tr><td>11</td><td>The before/after difference is canonical and self-checking</td>
<td>a difference that would understate the real change raises instead of reporting</td>
</tr>
<tr><td>12</td><td>Re-read before the write, read back immediately after</td><td>
Silpo's server answers a write with a success flag and the list of changed products —
no totals, no validations. That answer therefore cannot say whether the block cleared;
only a fresh read of the cart can</td></tr>
<tr><td>13</td><td><b>Checkout, payment and age confirmation stay the Customer's
own</b></td><td>a list in code, not a sentence in a comment, so a test can check it</td>
</tr>
</table>

<h2 id="graph">How one request is processed</h2>
<p>One customer request is processed as a sequence of steps, each next one chosen by
the result of the last: read → diagnose → compare channels → plan → collect and gate →
rank → explain →
<em>wait for consent</em> → write guard → write and read-back → persist receipt.</p>
<p>At the consent step processing stops — and nothing is left hanging in memory. The
intermediate state (the cart as read, the diagnosis, the proposed options) is written to
the database and the request that produced it ends: the service holds nothing and waits
for nobody. When the Customer presses the consent button that is a new request: the
service loads the saved state and continues from exactly the step it stopped at — even
if it was restarted meanwhile, or the request landed on a different worker process.</p>
<p>The diagram below is the standard shape of a LangGraph application, without project
detail: a typed state feeds a builder that compiles to an executable graph, a
conditional edge routes each step, and a checkpointer persists the state after every
node — which is what makes stopping for a human answer possible at all. This project's
own node topology is on the <a href="safety.html#compensation">safety page</a>.</p>
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
products, change the cart. The list is fetched from the server live, through
<code>tools/list</code>, and held only briefly, with an expiry.</p>
<p>For each tool the system keeps <b>a checksum of its description</b> — a short
signature computed from the parameters and their types, which changes the moment the
server alters anything in it. Beside it, in the repository, sits the list of tools
already reviewed together with their signatures; a developer refreshes that list with a
separate command, once they have looked at a change and accepted it.</p>
<p>If a tool appears for the first time, or its present signature does not match the
reviewed one, the system puts it in <b>quarantine</b>. In practice that means the tool
never enters the list the language model sees, and no step of the run calls it. The
Customer's current request does not stop: reading the cart, the diagnosis and the
product search carry on with the remaining, reviewed tools. What stops is only what is
impossible without the quarantined tool: if it was the write tool that changed, the
Write Guard refuses the write and says plainly that Silpo's service changed its
interface. A tool does not leave quarantine on its own — a developer looks at what
changed and, if it is acceptable, refreshes the reviewed list.</p>
<p>And about the description texts. The server sends a description with each tool, and
those descriptions are written for a general shopping assistant. The product-search
tool, for instance, carries the instruction "if user mentions a budget, ALWAYS fill the
cart as close to the budget limit as possible" (verbatim, from the tool-list snapshot of
5 September). For an assistant whose user has just said "I have a thousand hryvnias",
that is sound advice.</p>
<p>Lantern's task is narrower: the Customer named no budget — they have a blocked cart
and a specific shortfall. A model that took that instruction personally would offer more
than is needed to clear the block. That serves neither the Customer nor Silpo: an offer
the Customer declines does not become a completed order, and the completed order is what
both sides are after.</p>
<p>So the planner is given only the tool's name and the list of its parameters; the
description text is dropped before the model sees anything. The rule is wider than this
one example: any text arriving from an external server is data to us, never an
instruction to the model, whoever wrote it and with whatever intent.</p>
<div class="diagram">{{ mcp_adapter_svg }}</div>
<p>Step by step, when the agent needs the tool list: it asks the local store; if the
entry has expired the store fetches it from Silpo's server; the names are compared with
the previous list; and only then are the tools handed to the agent.</p>
<p>There is one more check — on the size of the answer. If the server ever returned more
than 500 tools, or more than 5 MB, the answer is rejected without being parsed. That is
a guard against a corrupted or deliberately inflated response: parsing one would spend
memory and time on data the system does not trust anyway. The ceilings are set with room
to spare — the largest answer Silpo's server has returned so far held 40 tools.</p>
<p>If such an answer did arrive, the Customer's request ends with an error: the service
says the tool list could not be read and does nothing further. The stale list is not
used instead — working from a list that may already have changed would mean calling a
tool with an unknown set of parameters, exactly what quarantine and the signature check
exist to prevent.</p>
<div class="diagram">{{ tools_list_svg }}</div>

<h2 id="domain">The domain core</h2>
<p>The data models that describe one recovery, from a raw cart to a receipt: cart,
validation, blocker, diagnosis, proposal, consent, receipt.</p>
<p>Along with the cart the server returns a list of <b>validations</b> — messages about
its state, each with a level: error, warning or informational. A validation at error
level is what stops the order being placed; those the system calls <b>blockers</b>. The
rest are still shown to the Customer — and it is among them that the constraint the app
displays nowhere turns up.</p>
<p>The core reads the cart and produces a <b>diagnosis</b>: exactly how many hryvnias
are missing. This is neither an estimate nor an answer from the language model — the
threshold comes from the validation's own data (<code>699</code> in
<code>orderCostMin</code>), the products total from the cart, and the system subtracts
one from the other.</p>
<p>The diagnosis is then used like this: it goes into the request to the language model,
which proposes search terms. Products that come back with a verified price and
availability are turned into concrete proposals by code — which computes the quantity
from the shortfall rather than asking the model for it. When the Customer agrees to one
of them the server records the consent; only the Write Guard may use that record.</p>
<p>None of these data models reach outside — not to Silpo's server, not to the language
model, not to the database. That is why every rule about them is checked by ordinary
tests, with no network call at all.</p>
<div class="diagram">{{ domain_class_svg }}</div>
<p>The next diagram follows one cart from the server's answer to the message the
Customer sees. First the answer is unpacked into known fields: totals, products,
validations. If its shape is unexpected — a required field missing, a type that does not
fit — processing stops at once with a named error and the Customer is told the cart
could not be read: better to say so than to compute a shortfall from data the system
does not trust.</p>
<p>If the answer unpacked cleanly, the system looks for the minimum-order threshold and
subtracts the products total from it. It also happens that the threshold is in none of
the known fields — then the Customer still gets a message, but one that says plainly
that the amount could not be confirmed; an invented number never takes its place.</p>
<p>Wherever the path leads, the message to the Customer lists <b>every</b> validation
the cart carries, not only the one that caused the block. From the audit of 10
September: the server returned two. The first is an error about the minimum order sum —
that is what blocks checkout, and the Silpo app shows it as a large button. The second
is informational: paying in instalments is unavailable because the cart is under 1000 ₴.
A Customer could only meet that on the payment screen — and while the cart is blocked by
the minimum, they never reach checkout, so it is shown to them nowhere at all. That
difference between what the server knows and what the Customer
sees is what Lantern exists to show.</p>
<div class="diagram">{{ domain_activity_svg }}</div>

<h2 id="planner">Planner, evidence gate, ranking</h2>
<p>After the diagnosis the language model sees what is already in the cart and how much
is missing, and proposes <b>search terms</b> — product or category names such as "milk",
"bread", "coffee". That is all it can return: there is no field for a price or a product
id in the shape it answers with. Its answer is a guess about <i>what to look for</i>,
and it decides nothing.</p>
<p>With those words the system queries Silpo's product search — in the same branch and
for the same delivery slot as the cart. The search returns a structured answer: name,
price, availability, identifiers. A candidate goes further only if its <b>price and
availability come from that same answer</b>: one with no confirmed price, or marked
unavailable, is dropped. The model has no part in those numbers.</p>
<p>For each survivor the system computes the smallest quantity that closes the
shortfall: the shortfall divided by the price, rounded to the catalogue's selling step
and capped by stock. It then orders the candidates <b>by one thing only — the top-up
amount, smallest first</b> — and shows the Customer the top two or three.</p>
<p>It is worth saying plainly what is <b>not</b> used to choose. The search is confined
to the same branch, delivery type and slot as the cart — otherwise the product found
could not be ordered at all. After that only the evidence gate filters: a confirmed
price and availability pass, anything else does not. Customer preferences, food
restrictions, favourites, promotions or semantic closeness to what is already in the
cart are <b>not</b> taken into account: Silpo's server offers tools for those, and this
version does not use them. The reason is plain: every extra signal is one more place to
be wrong in front of a Customer, and there was no measured way to validate relevance
within this version. So relevance stays with the model and with the Customer, who picks
one of two or three offers — or none.</p>
<div class="diagram">{{ g4_activity_svg }}</div>
<p>The next diagram shows the two places where a language model is involved at all, and
what each of them receives. Step by step: the system takes the tool list and keeps from
each tool only its name and the list of its parameters with their types; passes that to
the model together with the cart data and the shortfall; the model returns search
terms; the product search runs on them, and each result goes through <b>the evidence
gate</b> — a step of Lantern's own, with no model involved, which drops anything without
a confirmed price and availability in that same search answer. Once a candidate is
chosen the model is called a second time — to
write one Ukrainian sentence about that product; the product name is passed as plain
data, so no text inside it can become an instruction. Neither call ever sees the raw
tool descriptions, or the write tool.</p>
<div class="diagram">{{ g4_sequence_svg }}</div>
"""

RECOVERY = """
<p class="lede">The one scenario the project exists for, and what happened when it was
run live through the browser.</p>

<h2 id="flow">The flow</h2>
<p>A Customer's cart is under the minimum order sum. The agent reads the cart, lists
every
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
screen a Customer can reach</td></tr>
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
pure — and the session's spend beside the project ceiling. Middle: the Customer card, in
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
401 until the Customer logs in again</td></tr>
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
Customer-only action (checkout, payment, age confirmation), or it is
quarantined</td></tr>
<tr><td>The tool's schema</td><td>the hash of the schema the server returns now differs
from the reviewed one — the server changed its interface mid-session</td></tr>
<tr><td>The consent</td><td>it expired, it was already used, or it belongs to a
different action, owner or session</td></tr>
<tr><td>The cart</td><td>the cart re-read a moment before the write no longer matches
the one the Customer agreed about — someone changed it in another tab</td></tr>
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
<p>A refusal is terminal for the ordinary path, and the Customer is told which of the
reasons above it was, in plain Ukrainian rather than in the wording of the code.</p>
<div class="diagram">{{ g5_refusal_svg }}</div>

<h2 id="compensation">Undoing a change the Customer did not want</h2>
<p>A verified write is not a recovered cart. When a write left an unwanted diff, the
Customer is offered a compensation — a second, separately allowlisted tool,
re-authorised
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
<p>Before/after figures from moderated Customer sessions (n = 0 — no access to
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
<tr><td><code>sessions</code></td><td>one Customer's visit</td><td>the thread the graph
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
is never deleted and the audit trail survives a logout. Nothing stores the Customer's
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
