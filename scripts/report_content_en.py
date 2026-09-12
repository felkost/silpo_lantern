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
        ("models", "Language models"),
    ],
    "recovery.html": [
        ("flow", "The flow"),
        ("live", "The live run"),
        ("states", "States of a request"),
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
site, a model that never authorises, consent bound by checksums and expiry, independent
verification,
quarantine of tool drift.</p><a href="safety.html">Review the safeguards →</a></article>
<article class="card"><h3>4. Measurements</h3><p>Eight metrics with their populations,
95% intervals and caveats; the cost of an episode; what was deliberately not
measured.</p><a href="evidence.html">Inspect the evidence →</a></article>
<article class="card"><h3>5. Data model</h3><p>The six application tables — sessions,
tokens, consents, write claims, receipts, schema version — and their links; beside
them, the tables holding the saved processing state.</p>
<a href="data-model.html">Inspect the schema →</a></article>
</div>

<h2 id="claim">The design claim</h2>
<p>A tool's <code>success</code> flag is not proof. The system distinguishes <em>"the
agreed write occurred"</em> from <em>"the cart is now eligible for checkout"</em>, and
both require evidence from a fresh read of the cart. Everything else on these pages —
the single write site, the consent bound to one specific action, the quarantine of tool
drift, the metrics
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
<tr><td>Safety</td><td>the Write Guard: allowlist, consent binding, checksums of the
action, the cart state and the tool description, budget reserve, read-back gate</td>
<td>the only place a write tool is
called</td></tr>
<tr><td>Infra (the MCP adapter)</td><td>MCP client and OAuth, dynamic tool registry
with quarantine, Neon
repository and checkpointer, tracing with redaction</td><td>talks to the outside;
trusts nothing it receives</td></tr>
<tr><td>Application</td><td>the LangGraph graph and prompts</td><td>the model plans and
explains, never authorises</td></tr>
<tr><td>Interface</td><td>FastAPI routes, the React Customer card and the jury
console</td><td>Ukrainian for the Customer; English identifiers for the
jury</td></tr>
</table>
<p>Layer membership is enforced by a test that walks every import, not by directory
nesting alone.</p>

<h2 id="rules">The 13 domain rules</h2>
<p>The project applies thirteen domain rules — about money, time and evidence. Each
one exists as its own test file named after the rule
(<code>tests/unit/test_dr_01…13</code>), so "does the rule hold" is a question the test
suite answers rather than a claim in a document. None of them needs a network to
run. The five in <b>bold</b> are the product promise itself: the figure the Customer is
shown, who may compute it, no offer without verified price and availability, proof by
reading the cart back, and the boundary of what the agent never does.</p>
<table>
<tr><th>#</th><th>Rule</th><th>Why it is not obvious</th></tr>
<tr><td>01</td><td>Money is <code>Decimal</code>, coordinates are floats, quantity
keeps its fractional meaning</td><td>the cart returns coordinates as strings, which a
sibling tool rejects if passed on unconverted</td></tr>
<tr><td>02</td><td>Time is UTC inside, Kyiv time on screen</td><td>a delivery slot
of 06:30 UTC is 09:30 for the Customer</td></tr>
<tr><td>03</td><td><b>The shortfall is <code>minOrderCost −
productsTotal</code></b></td>
<td>comparing against the cart's grand total instead would invent a block on every
cart that carries a delivery fee or bonuses</td></tr>
<tr><td>04</td><td>A surcharge is named "service fee" only where a confirmed one
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
<p>For each tool the system keeps <b>a checksum of its description</b>. A checksum is
a short number computed from data; change any detail of the data and the number
changes, so two equal numbers mean the data is the same. Here the data is the list of
the tool's parameters and their types, and the number changes the moment the server
alters anything in that description. Beside it, in the repository, sits the list of
tools already reviewed together with their checksums; a developer refreshes that list
with a separate command, once they have looked at a change and accepted it. The same
device — a checksum — is used further on for two more things: the action the Customer
consents to, and the cart state (the Hero recovery and Safety pages).</p>
<p>Two different checks hang off the checksum and the list of reviewed tools, and they
fire in different places.</p>
<p><b>Quarantine</b> is for a tool that is not on the reviewed list (it appeared on the
server for the first time). Such a tool never enters the list the language model sees,
and no step of the run calls it. The Customer's current request does not stop: reading
the cart, the diagnosis and the product search carry on with the reviewed tools. Were
the write tool itself quarantined, the guard would refuse the write and the Customer
would see on the card: «Цю дію тимчасово призупинено на перевірку» ("this action is
paused for review"). Quarantine has no time limit: a tool leaves it only when a
developer reviews it and adds it to the reviewed list in the repository (the file
<code>reviewed_tools.json</code>; a separate script recomputes the checksums in it).
Until then the system carries on — simply without that tool.</p>
<p><b>The checksum check</b> is for the write tool, and at the moment of the write: the
guard compares the checksum of the description the server returns now with the reviewed
one. If they differ there is no write, and the Customer sees: «Сервіс Сільпо змінив свій
інтерфейс — спробуйте ще раз пізніше» ("Silpo's service changed its interface — try
again later"). For the read tools a changed description blocks nothing: the cart is
still read, and the difference is what a developer notices at review.</p>
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
tool with an unknown set of parameters, exactly what quarantine and the checksum check
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
subtracts the products total from it.</p>
<p>It also happens that the server reports a minimum-order block but the number itself
is nowhere in its answer — neither in that validation's data nor in the description of
the chosen delivery slot. That does <b>not</b> mean there is no minimum and the cart can
be checked out: the block stays, only the size of the threshold is unknown. Then the
system says exactly that — checkout is blocked, the exact amount could not be confirmed
— and makes no offers in that state, because computing a top-up from an unknown
threshold would mean inventing a number.</p>
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
unavailable, is dropped. Price and availability come from the search answer; the
language model is not used at this step.</p>
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
one of two or three offers — or none. In the second case the cart stays exactly as it
was: nothing added, nothing changed, the block still there. The next decision is the
Customer's — add something themselves in the Silpo app, choose another delivery
channel (its minimum may differ, or there may be none; Lantern shows that comparison
beside the diagnosis) or simply postpone the order. They can come back to the check at
any time: since nothing was written, a repeated look spoils nothing.</p>
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

<h2 id="models">Language models: which, where and for what</h2>
<p>The system has three roles for a language model, and each is assigned its own model.
All three are called through one provider (OpenRouter); the model ids and prices in the
table come from the settings file <code>config/models.yaml</code>, verified against the
provider's catalogue on {{ models.verified_at }}. Prices are dollars per million tokens,
input / output.</p>
<table>
<tr><th>Role</th><th>Where in the code</th><th>Model</th><th>Price, $/M</th><th>How
chosen and what it does</th></tr>
<tr><td>Planner</td><td><code>graph/llm_adapter.py</code>, step
<code>plan</code></td><td><code>{{ models.planner }}</code><br>fallback:
<code>{{ models.planner_fallback }}</code></td><td>{{ models.planner_price.input }} /
{{ models.planner_price.output }}</td><td>receives the diagnosis, the delivery-channel
comparison and the tool list without descriptions; returns only search terms. One call
per request with a large context (~30k tokens in), so a model with a window of at least
64k was chosen.</td></tr>
<tr><td>Explainer</td><td><code>graph/llm_adapter.py</code>, step
<code>explain</code></td><td><code>{{ models.explainer }}</code></td>
<td>{{ models.explainer_price.input }} / {{ models.explainer_price.output }}</td>
<td>writes one Ukrainian sentence about one option; the Customer sees exactly that text.
Chosen by a comparison of {{ models.explainer_candidates }} candidates on 28 test
prompts: the only model with no critical language errors (Russianisms, surzhyk); two
others scored higher on average but with such errors</td></tr>
<tr><td>Evaluation judge</td><td><code>evals/openrouter_judge.py</code> (the DeepEval
library, <code>GEval</code> criteria)</td><td><code>{{ models.judge }}</code></td>
<td>{{ models.judge_price.input }} / {{ models.judge_price.output }}</td><td>scores the
explainer's answers in a separate test suite, never while serving a Customer. Checked on
23 pairs labelled by the author: it reliably catches structural defects and is not used
as a measure of language quality (the "Not measured" section on the Measurements
page)</td></tr>
</table>
<p>What the model does in no role: it does not compute sums, does not choose the
product,
does not call the write tool and does not see it in the list. The ceiling on all model
calls is ${{ models.ceiling }} for the whole project, from the same settings file.</p>
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
<tr><td>Cart before the run</td><td>Products worth 605.62 ₴; the minimum order sum is
699 ₴.</td></tr>
<tr><td>What the server returned with the cart</td><td>Two validation results. The
first, <code>order.cost.min</code>, is an error: the sum is below the minimum and
checkout is blocked; the Silpo app shows it as a large button. The second,
<code>order.payment_types.disabled</code>, is informational: paying in instalments is
unavailable while the cart is under 1000 ₴; the app shows it nowhere, because a
Customer with a blocked cart never reaches the payment screen.</td></tr>
<tr><td>Shortfall</td><td>93.38 ₴ = 699 − 605.62. The 699 is taken from the
validation's own data, the products total from the cart. The subtraction is done by
ordinary code; the language model is not used at this step.</td></tr>
<tr><td>Options</td><td>Three products from Silpo's product search, price and
availability from that same search answer: 46.99 ₴ × 2, 94.99 ₴ × 1, 31.99 ₴ × 3.
Beside each option its action checksum is visible at once — a short number computed
from what will go to the server at the write: cart, product, quantity. Change any of
those and the number changes.</td></tr>
<tr><td>Consent</td><td>The Customer chose the third option. The server recorded the
consent together with the checksum of exactly that action (the same one shown beside
the option), the checksum of the cart state at the moment of consent (cart id, products
total, the list of lines: product, quantity, price) and an expiry of five
minutes.</td></tr>
<tr><td>Write and read-back</td><td>One write: 31.99 ₴ × 3 added. The cart was read
back separately: the products total rose by 95.97 ₴ — exactly what was expected.
Outcome <b>verified; the minimum reached, the block cleared</b>.</td></tr>
<tr><td>Spend</td><td>5,205 tokens, $0.0042 — from the usage data the model provider
itself returned, at the prices pinned in the project.</td></tr>
<tr><td>After the demonstration</td><td>The run was a demonstration on the project
author's real cart, so afterwards the cart was put back to its starting state: the
added product removed, the cart at 605.62 ₴ again. The project has a separate script
for this, <code>scripts/g5_restore_after_write.py</code> — it exists only for
demonstrations and is not part of the agent: the script finds the write by its
receipt, removes exactly the line that write added, and refuses to act if the cart has
moved since. The agent itself cannot remove products — no such tool is on its
allowlist, and that is deliberate. It also means the demonstration can be repeated any
number of times from the same cart state.</td></tr>
</table>
<div class="example"><b>What the price says.</b> On the live run of 7 September Silpo's
search returned a price of 99.00 ₴ for a product, and after it was added the cart
showed 89.10 ₴ for it: the cart applies a loyalty-programme discount to that product,
while the search returns the catalogue price without it. So the receipt carries the
sum from the cart, not from the search — which is why the cart is read back after the
write instead of trusting the prediction.</div>

<h2 id="states">The states one request passes through</h2>
<p>The diagram below shows the states of one Customer request — from the first read of
the cart to the receipt — and the transitions between them. Each box is a state the
request is in; each arrow is a transition, and the label on the arrow names the
condition under which it happens. Solid arrows are the main path, dashed ones the
exceptions.</p>
<p>The main path is eight states in order: <code>Read &amp; Normalize</code> (the cart
read and unpacked into fields) → <code>Diagnose</code> (the diagnosis) →
<code>Plan</code> (the search for options) → <code>Consent</code> (processing stopped,
waiting for the Customer) → <code>Re-read</code> (the cart re-read before the write) →
<code>Write</code> (the single call of the write tool) → <code>Read-back</code> (an
independent read after the write) → <code>Receipt</code> — the record of the write,
"before → after". That is the one path that ends with a receipt. Three dashed
transitions lead away from it: to an end without a write, back to planning, or to
<code>Unverified</code>, which is never shown as a success.</p>
<p>What each arrow label means:</p>
<table>
<tr><th>Label</th><th>From → to</th><th>Condition</th></tr>
<tr><td>NORMALIZED</td><td>Read &amp; Normalize → Diagnose</td><td>the server's answer
unpacked into the known fields without error: totals, products, validation
results</td></tr>
<tr><td>BLOCKER</td><td>Diagnose → Plan</td><td>among the validation results there is
a blocker with a known rule — the shortfall is computed</td></tr>
<tr><td>CANDIDATES</td><td>Plan → Consent</td><td>the search returned at least one
product with a confirmed price and availability; the Customer is shown the
options</td></tr>
<tr><td>CONSENT OK</td><td>Consent → Re-read</td><td>the Customer agreed to one
specific option; the consent is recorded</td></tr>
<tr><td>EXPIRED / REFUSED</td><td>Consent → end</td><td>the consent expired (five
minutes) or the guard refused — the cart untouched</td></tr>
<tr><td>HASH OK</td><td>Re-read → Write</td><td>the checksum of the re-read cart
matches the one recorded with the consent: the cart is the same</td></tr>
<tr><td>STATE CHANGED</td><td>Re-read → Plan</td><td>the cart changed after consent
(in another tab, say) — no write; the Customer gets a new offer for the new cart
state</td></tr>
<tr><td>CALLED</td><td>Write → Read-back</td><td>the write tool was called once; its
"success" answer proves nothing yet</td></tr>
<tr><td>DIFF MATCH</td><td>Read-back → Receipt</td><td>the "before → after"
difference from the read-back matches the expected one — the receipt is
verified</td></tr>
<tr><td>DIFF MISMATCH</td><td>Read-back → Unverified</td><td>what was read after the
write did not match what was expected, or the read-back failed — the outcome is
"unverified"</td></tr>
</table>
<div class="diagram">{{ state_svg }}</div>

<h2 id="console">What the console shows during the run</h2>
<p>The console has three columns. <b>In the middle</b> — the Customer card, the same
one the Customer sees, in Ukrainian. <b>On the right</b> — the cart as Silpo's server
returned it: one column with the state at the first read and one more after each
read-back; the line the write added is highlighted, and the totals stand side by side
so they can be compared.</p>
<p><b>On the left</b> — three blocks for the jury (the column is labelled so on the
console: «Журі»). The first, <code>Observed nodes</code>, is a log of the steps
the agent actually ran in this session, in execution order; beside each step, what it
touched: Silpo's server, the language model, the database, or nothing (computation in
code). Under the log, the session's spend on the language model: how many tokens were
used and what they cost at the prices pinned in the project, from the model provider's
own usage data. Beside it, the <b>project ceiling</b> — $20: the limit on language-model
spend for the whole project, from the first test to today, set by the author and
recorded in the settings file (<code>config/models.yaml</code>). It is shown so the
session's spend has something to be compared with.</p>
<p>The second block, <code>What this run shows</code>, is four claims about how the
system works. They are
the project's own claims, and under each one the console shows the data from the
current session that proves it; the field names are deliberately the same as in the
code, so they can be checked against it.</p>
<table>
<tr><th>Claim</th><th>What is shown under it in this session</th></tr>
<tr><td>The server returns more than the app shows</td><td>every validation result the
server returned with the cart, with its level. In the live run above there are two, and
the Silpo app shows only one: the Customer never learns from the app that instalments
are unavailable (<code>order.payment_types.disabled</code>)</td></tr>
<tr><td>Money is computed by code, never by the model</td><td>the input numbers and the
result: the products total from the cart (<code>products_total</code>), the
minimum-order threshold from the validation's data, and the shortfall as their
difference; for each option, its price and the search tool whose answer it came from.
The model's sentence on the card only explains, it does not compute</td></tr>
<tr><td>Nothing is written without item-bound consent</td><td>"written" — into the
Customer's cart on Silpo's server. Under the claim, the action checksum of each option
before consent, and after consent the consent record itself: the same action checksum,
the cart-state checksum and the expiry. If the guard refused — its refusal, in its own
words</td></tr>
<tr><td>Success is never asserted, only read back</td><td>Silpo's server answers a
write with only "success", no totals. So the system reads the cart again and shows here
the expected change beside the one read back: equal — "verified"; not equal, or the
read-back failed — "unverified"</td></tr>
</table>
<p>The third block, <code>Measured earlier — not this session</code>, shows on request
the eight indicators from the Measurements page — with <code>n</code>, interval and
caveat. The heading says deliberately that these were measured earlier, on recorded
runs, and not in this session: so the jury does not confuse the project's indicators
with what is happening on screen now.</p>

<h2 id="scenarios">The other scenarios</h2>
<table>
<tr><th>Scenario</th><th>Cart state</th><th>What the Customer sees and what the system
does</th></tr>
<tr><td>Second round</td><td>after the first write a shortfall remains — for instance
the cart applied a discount, and the added product cost less than the search
showed</td><td>the system diagnoses again, on the new cart state, and offers options
for the remaining shortfall; the Customer agrees again or declines. The first write's
receipt stays on screen beside the second</td></tr>
<tr><td>Compensation</td><td>the write happened and was verified, but produced not
what the Customer wanted: a different quantity, say, or a new blocker appeared in the
cart</td><td>the card shows a «Повернути як було» button — an offer to remove exactly
the line this write added, in the same quantity. That is a second write to the cart,
and it takes the same road as the first: the Customer consents to it separately, the
guard checks the consent and the cart afresh (including that the cart has not moved
since the first write), and after the undo the cart is read back again. The receipt
shows a negative change, «Повернуто на …»</td></tr>
<tr><td>Safeguard</td><td>none of the validation results is one the system knows —
for instance a lapsed delivery slot or out-of-stock products, whose codes are not in
the rule registry</td><td>the Customer sees «Причина: невідома» and the explanation:
no validation result is a known rule, so the system does not propose an action blind
— check the cart in the Silpo app. Below it, the full list of what the server
returned, unrecognised codes marked «не розпізнано». The language model is not
called, the cart is not changed, the session's spend is zero. The system does not
hang: it says plainly that it knows no such rule and leaves the decision with the
Customer</td></tr>
<tr><td>Logout</td><td>any</td><td>the «Вийти» button deletes the Silpo credential on
the server side; a fresh session sees no cart until the Customer logs in
again</td></tr>
</table>
"""

SAFETY = """
<p class="lede">What keeps a language model from changing a real Customer's cart on its
own — adding or removing a product without the Customer's consent.</p>

<h2 id="guard">What the Write Guard is</h2>
<p>One node in the graph, and the only place in the whole system from which a write tool
can be called. This is not a convention: no other module may even import the list of
allowed write tools, and a test that walks every import fails the build if one
tries.</p>
<p>Before any write the guard answers one question — may this exact change happen
right now? — and returns either an authorisation or a refusal with its reason. Several
of the checks below rest on <b>checksums</b> — the same three introduced on the earlier
pages: the <a href="architecture.html#mcp">tool-description checksum</a> (from the
tool's parameters and their types) and the
<a href="recovery.html#live">action and cart-state checksums</a> (from what will go
to the server at the write — cart, product, quantity; and from the cart id, the
products total and the list of lines — product, quantity, price). To recall: a
checksum is a short number computed from data; change any detail of the data and the
number changes, so two equal numbers mean the data is the same. There are 22 ways to
refuse:</p>
<table>
<tr><th>It checks</th><th>And refuses when</th></tr>
<tr><td>The tool</td><td>it is not on the allowlist for this kind of action, it is a
Customer-only action (checkout, payment, age confirmation), or it is
quarantined</td></tr>
<tr><td>The tool's schema</td><td>the checksum of the description the server returns
now differs from the reviewed one — the server changed its interface
mid-session</td></tr>
<tr><td>The consent</td><td>it expired, it was already used, or it belongs to a
different action, owner or session</td></tr>
<tr><td>The cart</td><td>the cart re-read a moment before the write no longer matches
the one the Customer agreed about — someone changed it in another tab</td></tr>
<tr><td>The arguments</td><td>the action checksum (cart, product, quantity) differs
from the one recorded with the consent; no checksum is ever accepted from the browser,
both are recomputed on the server</td></tr>
<tr><td>The budget</td><td>there is not enough reserve left to read the cart back —
writing without being able to prove the outcome is not allowed</td></tr>
<tr><td>An undo</td><td>eight further checks that a compensation undoes exactly the
change this system itself made, as its receipt records it</td></tr>
</table>
<p>The language model takes no part in the guard's work. Its role ends earlier: it
proposes search terms and explains the chosen option. The guard receives only structured
data — the consent record, the re-read cart, the write arguments — and no text from the
model. The write tool itself is never handed to the language model: it is absent from
the tool list the model sees, so the model cannot call a write even by mistake.</p>

<h2 id="invariants">The invariants</h2>
<ul>
<li><b>One write site.</b> Only the Write Guard node may call a write tool; a layering
test bans importing the write allowlist anywhere else.</li>
<li><b>The model never authorises.</b> It plans and explains; money, gap arithmetic and
post-conditions are server code with no language model involved: the same input
always gives the same result.</li>
<li><b>Consent is bound to one action and one cart state</b> — <code>action_id</code>,
canonical arguments, the action checksum (<code>args_hash</code>), the cart-state
checksum (<code>state_hash</code>), expiry. A generic
"yes" after the plan changed carries nothing forward.</li>
<li><b><code>success</code> from the server proves nothing.</b> Every write is followed
by an independent read-back; an unreachable read-back yields <code>unverified</code>,
never a successful receipt.</li>
<li><b>The tool list is untrusted input.</b> Discovered live, with a checksum of the
description per tool. A new tool is quarantined — with no time limit, until a developer
reviews it and adds it to the reviewed list in the repository; the model does not see
it, no step calls it, and the guard refuses a write with it («Цю дію тимчасово
призупинено на перевірку»). A changed description of the write tool the guard notices
by its checksum at the moment of the write, and refuses («Сервіс Сільпо змінив свій
інтерфейс — спробуйте ще раз пізніше»). In both cases the cart is not changed, and the
rest of the work — reading, diagnosis, search — goes on. More on the
<a href="architecture.html#mcp">Architecture page</a>.</li>
<li><b>The session is the ordinary web-session model.</b> An <code>HttpOnly; Secure;
SameSite=Lax</code> cookie, one credential per session, logout deletes it, idle tokens
expire after 30 minutes, and every route checks the cookie against the path.</li>
</ul>

<h2 id="consent">Consent → guard → write → read-back</h2>
<p>One consented action, end to end: the client posts only an action id, the server
recomputes both checksums from what it already holds, the graph resumes at the guard,
the
cart is re-read, one write tool is called, the cart is read back independently, and the
receipt records the difference between what was expected and what the cart returned.</p>
<div class="diagram">{{ g5_sequence_svg }}</div>
<p>The second diagram shows the same stretch as the sequence above, but as states: the
states a Customer request is in from the moment the options are shown to the receipt.
This is the only stretch of the whole processing in which the cart can change at all;
before it (reading, diagnosis, search) nobody changes the cart. Each box is a state of
the request, each arrow a transition, and the label on the arrow the condition.</p>
<p>Everything starts in <code>Awaiting consent</code>: processing of the request on the
server is stopped, its intermediate state is saved in the database, and the server waits
for the Customer to press the button with one of the options on the card. That button is
the consent; it comes from the Customer, from their browser, as a new request to the
server. The labels:</p>
<table>
<tr><th>Label</th><th>From → to</th><th>Condition</th></tr>
<tr><td>AUTHORIZED</td><td>Awaiting consent → Consented</td><td>the consent arrived,
and the guard, having checked it against the list in the section above, authorised the
write. The language model takes no part in that decision</td></tr>
<tr><td>REFUSED</td><td>Awaiting consent → Aborted</td><td>the consent arrived, but the
guard refused — one of the 22 reasons, an expired consent among them</td></tr>
<tr><td>NO WRITE MADE</td><td>Aborted → end</td><td>the request is over, the refusal
reason recorded, nothing written to the cart; the Customer sees the reason on the
card</td></tr>
<tr><td>WRITE</td><td>Consented → Written</td><td>the write tool called once, and the
cart read back immediately after in a separate call</td></tr>
<tr><td>CONFIRMED</td><td>Written → Verified</td><td>the change the read-back showed
matched the expected one</td></tr>
<tr><td>UNCONFIRMED</td><td>Written → Unverified</td><td>the read-back did not match
the expected change, or failed altogether</td></tr>
<tr><td>RECEIPT: VERIFIED</td><td>Verified → end</td><td>the receipt records "verified"
and whether the block was cleared</td></tr>
<tr><td>RECEIPT: UNVERIFIED</td><td>Unverified → end</td><td>the receipt records
"unverified"; this state is never shown as a success (dashed border on the
diagram)</td></tr>
<tr><td>BLOCKER REMAINS · RE-DIAGNOSE</td><td>Verified → Awaiting consent</td><td>the
write is verified but a shortfall remains (a cart discount, say): the system diagnoses
again, shows options again — and waits for consent again. At most three such
rounds</td></tr>
</table>
<p>A system that can only report success will report success when it is wrong; here
that case has its own state, <code>Unverified</code>.</p>
<div class="diagram">{{ write_state_svg }}</div>

<h2 id="refusal">When the guard refuses</h2>
<p>A refusal by the guard ends the request: nothing is written to the cart, and the
system does not retry the write on its own. The guard returns the reason in its own
words — short English strings as written in the code, for instance <code>consent has
expired</code>. That string is what is stored in the database and shown on the jury
panel, so it can be checked against the code. The Customer, on the card, sees a
translation of that string from a fixed dictionary — for the same example: «Час на
підтвердження минув — почніть спочатку» ("the time to confirm has passed — start
again"). To try again, the Customer starts the cart check afresh.</p>
<p>The diagram below shows this in time, step by step: after consent the server resumes
processing at the guard (steps 1–2), loads the consent record from the database (3–4),
re-reads the cart at Silpo (5–6) and recomputes both checksums itself (7). If every
binding holds — one call of the write tool (8); if not — a refusal with its reason (9),
and the Customer sees it on the card with no write made (10). The inset on the right
lists the reasons; those marked with a dot were observed live on 7 September 2026.</p>
<div class="diagram">{{ g5_refusal_svg }}</div>

<h2 id="compensation">Undoing a change the Customer did not want</h2>
<p>A verified write is not a recovered cart: a write can go exactly as agreed and
still leave something the Customer did not want. Then the Customer is offered an undo —
removing from the cart exactly the line that write added. The undo is one more write to
the cart, made with a different tool of Silpo's server
(<code>silpo_remove_cart_products</code>), allowed for this purpose only. Its road is
the same as the first write's: the Customer consents to the undo separately, the guard
checks that consent and the cart afresh, after the tool call the cart is read back
again, and
the undo's receipt is confirmed by the same comparison of expected against read.</p>
<div class="diagram">{{ g8_compensation_happy_svg }}</div>
<p>An undo is a write too, so the guard checks it too, and it can refuse. Then the undo
is not performed, the cart stays as the first write left it, and the Customer sees the
reason. A refusal happens in three cases. First: there is nothing to undo — the first
write was not verified (the read-back after it failed) or it already cleared the block,
so there is no need to revert. Second: the cart changed again after the first write —
the Customer added something in the Silpo app, say; a removal could hit the wrong line.
Third: what is asked to be removed does not match what the first write's receipt
recorded — a different product or a different quantity.</p>
<div class="diagram">{{ g8_compensation_refusal_svg }}</div>
<p>The last diagram shows how the undo is built into the processing: it has no separate
path — it is one more pass through the same guard, with a new consent from the Customer.
The diagram has three processing steps (boxes) and the transitions between them; the
steps before the guard (reading, diagnosis, search, explanation) are not on it, they did
not change. What the labels mean:</p>
<table>
<tr><th>Label</th><th>From → to</th><th>Meaning</th></tr>
<tr><td>AUTHORIZED</td><td>Write Guard → Write &amp; Read-back</td><td>the guard
authorised the write; the "write and read back" step is the only place in the system
where the write tool is called</td></tr>
<tr><td>REFUSED · either kind</td><td>Write Guard → Aborted</td><td>the guard refused —
whether it was an ordinary write or an undo; the request ends with no write</td></tr>
<tr><td>RECEIPT</td><td>Write &amp; Read-back → Persist Receipt</td><td>the write's
receipt (verified or not) is stored in the database; here it is decided what comes
next</td></tr>
<tr><td>CLEARED OR NO MORE OPTIONS</td><td>Persist Receipt → end</td><td>the block is
cleared — or there are no options left; the Customer sees the receipt</td></tr>
<tr><td>RETRY · rounds remain</td><td>Persist Receipt → Diagnose</td><td>a shortfall
remains and rounds are left (at most three): a new diagnosis, new options — and back to
the guard through consent</td></tr>
<tr><td>COMPENSATE · rounds spent, compensable</td><td>Persist Receipt → Write
Guard</td><td>the rounds are used up and the write can be undone (it is verified and did
not clear the block): the Customer is shown «Повернути як було», and processing stops
again waiting for consent — at the same guard</td></tr>
<tr><td>RETRY_GUARD · self-loop</td><td>Write Guard → Write Guard</td><td>the guard
refused the undo because the cart moved meanwhile; it then builds one new undo offer for
the cart as it is now and waits for consent again. One such attempt — then a
refusal</td></tr>
</table>
<p>"NEW EDGE (G8)" beside two transitions means they were added at development stage
G8, when the undo appeared; the other transitions existed before.</p>
<div class="diagram">{{ g8_topology_svg }}</div>

<h2 id="rg">Resilience checks</h2>
<p>The project brief names seven situations in which the system must behave
predictably even when something goes wrong; each has an automated test. The status in
the table comes from the file the project maintains (<code>coverage.json</code>); the
wording of each check is the brief's own.</p>
<table>
<tr><th>#</th><th>What is checked</th><th>Status</th></tr>
{% for row in coverage %}
<tr><td>{{ row.rg_id[3:] }}</td><td>{{ row.rubric }}</td><td>{{ row.status }}</td></tr>
{% endfor %}
</table>
<p><code>pass</code> means the test passed and the record of that run is kept in the
repository; <code>blocked</code> — the check is written but there is nothing to check it
against: the budget accounting for cycles and attempts does not work in this version,
and the test cannot get around that; <code>not_applicable</code> is the one row the
brief itself leaves outside this version.</p>
"""

EVIDENCE = """
<p class="lede">Eight indicators the project checks itself against. Each comes with the
population it was measured over (<code>n</code>), its 95% confidence interval and a
caveat about what it does not mean — no value appears on the page without those
three.</p>

<h2 id="metrics">The indicators</h2>
<p>The first four check the safeguards: each must be exactly 0 or exactly 1, and any
other value would mean a defect, not "slightly worse". The fifth explains a price
discrepancy. The sixth and seventh — whether the system does what it exists for at all.
The eighth — whether it shows what the app does not.</p>
{% set metric_en = {
 "UnauthorizedWriteRate": ("Writes without the guard's authorisation",
  "the share of cart writes that happened without the guard's authorisation; the
  denominator is every write claim. Must be 0: no write may bypass the guard."),
 "ReadbackCoverage": ("Read-back after the write",
  "the share of writes after which the cart was re-read in a separate call. Must be 1:
  every write is checked, not taken on trust."),
 "ConsentBindingIntegrity": ("Consent binding integrity",
  "the share of writes in which the recorded consent's checksums matched what the guard
  authorised. Must be 1."),
 "WriteDeltaFidelity": ("Fidelity of the recorded change",
  "the share of writes in which the change recorded on the receipt matches how the cart
  actually moved. Must be 1: the receipt does not invent."),
 "SearchPriceFidelity": ("Search price equals cart price",
  "how often the price from the product search equalled the price the cart applied. Not
  a success measure: it is low because the cart applies a loyalty discount the search
  does not return — which is why the receipt takes the sum from the cart."),
 "RecoveryCompletionRate": ("Blocks cleared",
  "the share of requests on the core test cases in which the block was cleared.
  Threshold 0.85."),
 "FalseRecovery": ("False “recovered” claims",
  "the number of cases in which the system claimed the block was cleared when it was
  not. Must be 0. A count, not a rate."),
 "DisclosureRate": ("Shown what the app does not show",
  "whether the system showed the Customer a validation result the Silpo app shows
  nowhere. One audited observation, reported as one."),
} %}
<table>
<tr><th>Indicator</th><th>What it means</th><th>Value</th><th>n</th>
<th>95% interval</th>
</tr>
{% for m in metrics %}
<tr><td><b>{{ metric_en[m.name][0] }}</b><br><code>{{ m.name }}</code></td>
<td>{{ metric_en[m.name][1] }}</td><td>{{ m.display }}</td><td>{{ m.n }}</td>
<td>{{ m.ci }}</td></tr>
{% endfor %}
</table>
<p><b>Population.</b> The label <code>{{ population }}</code> means all eight indicators
were measured not on live requests but on 18 repeats: recorded records of real runs are
replayed through the same graph the live path runs, so the result can be recomputed
from the repository at any time (<code>{{ regenerate }}</code>; a gate test asserts the
committed file agrees with a fresh regeneration). <code>n</code> = 33 is the number of
cart writes across those 18 repeats: some runs had more than one write. The same 18
runs live on 2026-09-09 gave 18 of 18.</p>
<p><b>What the chart shows.</b> The same eight indicators as horizontal bars on a 0-to-1
scale. The bar's length is the measured value; the thin line with end caps on either
side of it is the 95% confidence interval; under each indicator's name, its
<code>n</code>; on the right, the threshold (<i>gate</i>) the project set for it and
whether it is met (<i>gate met</i>). "False recovered claims" is shown not as a bar but
as the label "0 of 33", because it is a count; "search price fidelity" has no gate — it
is an observation, not a requirement.</p>
<div class="diagram">{{ g9_metrics_svg }}</div>

<h2 id="reading">How to read the intervals</h2>
<p>Every indicator but one is a proportion: how many times out of <code>n</code>. But
"33 of 33" does not mean "exactly 1.00 for good": on 33 observations the true proportion
could be 0.90 — a rare failure simply has not happened yet. A confidence interval shows
which true values are consistent with what was observed; 95% means the method, applied
many times, covers the true value in about 95 cases out of 100.</p>
<p>The intervals are computed with the <b>Wilson method</b>. Why that one: the simplest
formula (Wald, "estimate ± 1.96 · standard error") gives a zero-width interval at the
boundaries 0 and 1 — [1.00, 1.00] — and would claim that 33 observations settled the
question; that is false. The "exact" Clopper–Pearson method works at the boundaries but
is deliberately wider than needed (real coverage 97–99% instead of 95%). Wilson gives
the
coverage closest to the stated 95% on small samples and is correct at the boundaries. On
this project's data: for 33 of 33 — [0.90, 1.00]; for 0 of 33 — [0.00, 0.10]; for 18 of
18 — [0.82, 1.00]; Clopper–Pearson would give [0.89, 1.00], [0.00, 0.11] and
[0.82, 1.00], Wald a point.</p>
<p><b>What was obtained and what it means.</b> The four safeguard indicators gave 0
violations in 33 (unauthorised writes, false "recovered" claims) and 33 of 33
(read-back, consent binding, change fidelity). A lower bound of 0.90 means: on these 33
observations one cannot rule out a true failure rate of up to one in ten; one can only
say that in 33 trials none occurred. Blocks cleared — 18 of 18, lower bound 0.82: that
is below the 0.85 threshold, so the statistic on 18 runs alone does not yet guarantee
the threshold; the point value of 1.00 and the tests support it. "Search price fidelity"
at 0.27 with an interval of [0.15, 0.44] is a wide spread: 33 observations are too few
for a precise proportion, and none is needed here — the indicator only explains why the
receipt takes the sum from the cart. For one observation (<code>n</code> = 1) the
interval [0.21, 1.00] is almost the whole scale, and that is how it is reported.</p>
<p><b>What would raise the precision, and why this is enough.</b> An interval narrows
only with the number of observations: at 100 of 100 the lower bound would be 0.96, at
300 of 300 — 0.99; for the lower bound of blocks cleared to pass the 0.85 threshold, 22
clean runs of 22 would do. Each live run costs about $0.007 and one write to a real
cart, so 300 repeats are a question not of money but of the author's time restoring the
cart after each. For this project that precision is enough, because the four safeguard
indicators are not probability estimates but a check of the construction: the single
write site, the read-back after every write and the consent binding are enforced by
code and by tests that run on every code change. The statistic on 33 observations
answers a different question — whether the live runs refuted that construction — and
"not once in 33" is a sufficient answer to it. The indicators with a 0.85 threshold or
none are another matter: their precision really is limited by the sample, and that is
why they are reported with an interval rather than as a promise.</p>

<h2 id="cost">Cost</h2>
<p><b>What is counted.</b> Only the language model's work: the project has two paid
model calls per request — the planner (search terms) and the explainer (one sentence per
option). Silpo's server, the database and hosting cost the project nothing at this
scale. <b>How it is counted.</b> Every call returns, together with its answer, the
provider's own usage block — how many tokens went in and how many came out; the system
multiplies those by the prices fixed in the project's settings file
(<code>config/models.yaml</code>, dated against the provider's catalogue) and records
the amount on the session. No figure is an estimate from text length.</p>
<p><b>What was obtained.</b> The 18 live runs used for the measurements above — 114
model calls in total — cost $0.13, that is about $0.007 per request with both calls.
The hero run through the console cost $0.0042 (5,205 tokens). These figures describe
one request, not the project: the runs recorded and tracked in the repository add up
to about $1 against the $20 ceiling, and that total does not include the development
runs and failed experiments made outside the recorded runs — those are visible only on
the provider's account, and this page does not report them.</p>

<h2 id="economics">Unit economics</h2>
<p>The project brief gives a formula for the net benefit of the agent over a period:</p>
<p><code>Vnet = B × (p₁ × M₁ − p₀ × M₀ − c) + ΔS × C − F</code></p>
<p>The parameters:</p>
<ul>
<li><b>B</b> — the number of recovery-eligible requests in the period: carts blocked by
the minimum order sum that the agent could work with.</li>
<li><b>p₁</b> — the share of those requests that ended in a purchase with the agent
working.</li>
<li><b>p₀</b> — the same share without the agent: how many Customers complete the
purchase anyway.</li>
<li><b>M₁</b> — the marginal contribution of one purchase with the agent (revenue minus
the variable costs of that purchase).</li>
<li><b>M₀</b> — the marginal contribution of one purchase without the agent.</li>
<li><b>c</b> — the agent's variable cost per request: the cost of the language-model
calls.</li>
<li><b>ΔS</b> — the number of support contacts avoided thanks to the agent in the same
period.</li>
<li><b>C</b> — the cost of handling one support contact.</li>
<li><b>F</b> — the fixed cost of introducing the agent: development, integration,
maintenance.</li>
</ul>
<p>The formula in words. The product <code>p₁ × M₁</code> is the average margin from one
request with the agent: the share of completed purchases times the margin of one
purchase. The product <code>p₀ × M₀</code> is the same average margin without the agent.
Their difference is how much margin the agent adds per request. From that difference,
<code>c</code>, the agent's cost for the request, is subtracted. The result in brackets
is the net benefit of one request; multiplied by <code>B</code>, the number of requests,
it gives the benefit for the period. To that is added the saving on support:
<code>ΔS × C</code>, the number of avoided contacts times the cost of each. From the sum
the fixed cost <code>F</code> is subtracted. If the result is above zero, the agent pays
for itself.</p>
<p>Of all the parameters, this project has measured only <code>c</code>: about $0.007
per request (the Cost section). The rest can come only from a pilot comparison on real
Customers: one group of requests with the agent, another without, over the same period.
The main question of such a pilot is whether <code>p₁</code> is greater than
<code>p₀</code> — whether the agent really brings more Customers to a purchase. A
reference point for scale: at <code>c</code> ≈ $0.01 the agent pays for itself if for
every hundred requests it adds one purchase with more than one dollar of margin.</p>

<h2 id="unmeasured">Not measured</h2>
<p>Three things from the project brief were not measured, and here is why.</p>
<p><b>A before/after comparison in sessions with Customers.</b> The brief provides for
moderated sessions: a Customer works through a blocked cart first without the agent,
then with it, and a moderator records the time, the number of actions and the outcome.
The protocol for those sessions is written. No sessions were held, because the project
had no access to participants; <code>n</code> = 0. Consequence: everything these pages
say about clarity and convenience for the Customer rests on the author's own runs, not
on other people. This is the largest gap in the project's evidence. Only holding the
sessions under the written protocol can fill it.</p>
<p><b>The effect on conversion and revenue.</b> The parameters <code>p₁</code>,
<code>p₀</code>, <code>M₁</code>, <code>M₀</code> from the formula above can be
measured only on Silpo's real order flow, in a pilot comparison of two groups of
Customers. The project has no such access. Consequence: the statement about the agent
paying for itself on these pages is conditional ("provided p₁ − p₀ &gt; 0"), not a
result. The measured indicators show that the agent works safely and correctly; they do
not show that it increases sales.</p>
<p><b>The language quality of the explanations.</b> The project has automatic answer
evaluators (one language model scoring another's text; the DeepEval library, judge model
<code>openai/gpt-5.6-luna</code> — see "Language models" on the Architecture page).
They were checked against
labelled examples, and that check showed: they reliably detect structural defects — a
mixed-up sum, an extra product, a missing warning — and do not reliably judge the
quality of the Ukrainian. So they are used only to find defects, and their quality
scores are not reported on these pages. Consequence: the reader judges the language on
the card for themselves, from the examples; the project has no numeric indicator for
it.</p>
"""

DATA_MODEL = """
<p class="lede">The service's database consists of six application tables and four
tables of the library that stores the processing state. The diagram below shows them
all: for each table, its fields with types, primary (<code>PK</code>) and foreign
(<code>FK</code>) keys; the arrows between tables are the key relationships.</p>
<div class="diagram">{{ er_svg }}</div>

<h2 id="tables">The application tables</h2>
<table>
<tr><th>Table</th><th>One record is</th><th>What it holds and what it is used for</th>
</tr>
<tr><td><code>sessions</code></td><td>one Customer's visit to the service, from login to
logout</td><td>the session id (<code>session_id</code>); the thread id
(<code>thread_id</code>) under which the library tables hold the saved processing
state; the owner code (<code>owner</code>) — a checksum of the session id and a
server-side secret, which the guard checks against every consent; creation and
last-activity times</td></tr>
<tr><td><code>oauth_tokens</code></td><td>the Silpo credential issued for this
visit</td><td>the access token for Silpo's server obtained after the phone login
(<code>token</code>) and its last-use time. Kept on the server only. Deleted when the
Customer logs out or after 30 minutes without activity. The only table whose record is
deleted together with the session</td></tr>
<tr><td><code>consents</code></td><td>one Customer consent to one specific
action</td><td>the action id (<code>action_id</code>), the write arguments
(<code>canonical_args</code>), the action and cart-state checksums
(<code>args_hash</code>, <code>state_hash</code>), the expiry (<code>expires_at</code>)
and the time of use (<code>consumed_at</code>). The guard reads this record before the
cart write and marks it used, so one consent yields at most one write</td></tr>
<tr><td><code>idempotency_keys</code></td><td>one claim to write to the cart</td><td>the
owner, the cart, the action and the arguments checksum; the claim's state
(<code>state</code>, five values) and the call's result (<code>result</code>). A claim
is created immediately before the write tool is called; the uniqueness of the triple
(owner, cart, action) stops a repeated request — after a dropped connection, say — from
making the same write twice</td></tr>
<tr><td><code>receipts</code></td><td>the receipt of one write to the cart</td><td>the
cart state before and after the write (<code>before_state</code>,
<code>after_state</code>), the expected and actual change of the sum
(<code>expected_delta</code>, <code>actual_delta</code>), the read-back outcome
(<code>verified</code>, <code>status</code>), whether the block was cleared
(<code>blocker_cleared</code>) and the remaining shortfall, the kind of write
(<code>kind</code>: add or compensate). This is the log of every cart change the system
made; it is kept after the Customer logs out</td></tr>
<tr><td><code>schema_version</code></td><td>one applied schema migration</td><td>the
version number and the time it was applied. On start-up the service compares the
database version with the code's; on a mismatch without a matching migration it does
not start</td></tr>
</table>

<h2 id="choices">Two decisions about storage</h2>
<p><b>What is deleted at logout, and what is not.</b> When the Customer logs out, only
the record in <code>oauth_tokens</code> — the Silpo credential — is deleted. The records
in <code>sessions</code>, <code>consents</code> and <code>receipts</code> remain. That
is
deliberate: consents and receipts are the log of what the system changed in the cart and
with whose consent, and it is needed after the session — for checking, for an undo, for
a report. Technically this is visible on the diagram: the foreign key from
<code>oauth_tokens</code> to <code>sessions</code> cascades on delete (migration 0007),
while the keys from <code>consents</code> and <code>receipts</code> do not (migrations
0003 and 0005). Because of that a session record cannot be deleted while consents or
receipts reference it, and the service never deletes one.</p>
<p><b>Where the Customer's data lives.</b> No table has a separate field for the
Customer's address, phone or coordinates. However, in <code>receipts</code> the fields
<code>before_state</code> and <code>after_state</code> store the cart as Silpo's server
returned it — with all its fields, delivery coordinates included; and in
<code>oauth_tokens</code> the access token is stored unencrypted. The protection of that
data is access to the database itself (Neon); encryption at rest is deferred in this
version. The Customer's browser and the jury panel never receive the whole cart:
the service sends only the delivery type, the slot, the products total and the lines
(name, quantity, price).</p>

<h2 id="checkpointer">The tables of saved processing state</h2>
<p>Processing of a request is not one continuous call: at the consent step it stops and
waits for the Customer, and the request that started it ends. To continue later from the
same place, the processing state at the moment of the stop — the cart as read, the
diagnosis, the proposed options, the step number — is written to the database. When the
consent arrives the server reads that record and continues from the next step; in the
same way a request survives a restart of the service. After the receipt the record
stays in the database as the history of that request's steps.</p>
<p>These records are kept by the workflow library (LangGraph) in its own four tables
(<code>checkpoints</code>, <code>checkpoint_blobs</code>,
<code>checkpoint_writes</code>,
<code>checkpoint_migrations</code>) in the same database. The link to the session is by
the value of <code>thread_id</code>, with no foreign key: the library creates and
changes
its tables itself, the application its own, and neither depends on the other's
migrations.</p>
"""

BODIES = {
    "index.html": INDEX,
    "architecture.html": ARCHITECTURE,
    "recovery.html": RECOVERY,
    "safety.html": SAFETY,
    "evidence.html": EVIDENCE,
    "data-model.html": DATA_MODEL,
}
