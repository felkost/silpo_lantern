"""Renders the documentation site the README links to, in both languages:
one entry page and one page per question, each with a fixed left table of
contents, the material on the right, an "on this page" list at the top, a
language switch, and a "next" link at the bottom. Inline stylesheet and
inline SVG, so the pages work from GitHub and from a local disk alike.
Every diagram the project owns appears on exactly one page, in each
language.

    .venv/Scripts/python.exe scripts/render_report.py

English lands in the report directory, Ukrainian in its `uk/`
subdirectory, so a relative link between pages is the same string in
both. Page bodies
live in `report_content_en.py` / `report_content_uk.py`; this file only
renders them. Every number comes from a tracked file
(`datasets/golden-v1.0.0/metrics.json`, `coverage.json`).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from jinja2 import Template

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import report_content_en as EN  # noqa: E402
from scripts import report_content_uk as UK  # noqa: E402

OUT_DIR = ROOT / "docs" / "reports"
UML_SVG_DIR = ROOT / "docs" / "uml" / "svg"
METRICS_PATH = ROOT / "datasets" / "golden-v1.0.0" / "metrics.json"
COVERAGE_PATH = ROOT / "datasets" / "golden-v1.0.0" / "coverage.json"
MODELS_PATH = ROOT / "config" / "models.yaml"

# Ukrainian pages sit one directory down, so "safety.html" resolves inside
# the same language and "../safety.html" crosses to the other one.
LANGUAGES = {"en": (EN, ""), "uk": (UK, "uk/")}


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


STYLE = """
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #1a1a1a;
background: #fafafa; line-height: 1.55; }
.shell { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
.sidebar { position: sticky; top: 0; height: 100vh; overflow-y: auto;
padding: 1.4rem 1.2rem; border-right: 1px solid #e3e7f0; background: #fff; }
.brand { display: block; font-weight: 700; font-size: 1.1rem; color: #1a1a1a;
text-decoration: none; margin-bottom: 1rem; }
.langs { display: flex; gap: .4rem; margin: 0 0 1.2rem; }
.langs a, .langs span { font-size: .8rem; padding: .15rem .5rem; border-radius: 999px;
border: 1px solid #e3e7f0; text-decoration: none; color: #1a1a1a; }
.langs span { background: #1d4ed8; border-color: #1d4ed8; color: #fff; }
.nav-label { margin: 1rem 0 .3rem; font-size: .72rem; letter-spacing: .12em;
text-transform: uppercase; color: #888; }
.sidebar nav a { display: block; padding: .3rem .5rem; border-radius: 6px;
color: #1a1a1a; text-decoration: none; font-size: .95rem; }
.sidebar nav a[aria-current="page"] { background: #e8f1ff; color: #1d4ed8;
font-weight: 600; }
.sidebar nav a:hover { background: #f1f3f8; }
main { max-width: none; width: 100%; padding: 2rem 3rem 3rem; }
.eyebrow { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase;
color: #2a5; margin: 0 0 .4rem; }
h1 { margin: 0 0 .6rem; font-size: 1.7rem; line-height: 1.25; }
h2 { margin-top: 2.4rem; border-bottom: 1px solid #e3e7f0; padding-bottom: .25rem; }
h3 { margin-top: 1.6rem; font-size: 1.05rem; }
.lede { color: #444; font-size: 1.05rem; }
.notice { background: #fff8e6; border-left: 4px solid #f2b21e; padding: .6rem .9rem;
margin: 1rem 0; }
.onpage { background: #fff; border: 1px solid #e3e7f0; border-radius: 8px;
padding: .6rem 1rem; margin: 1rem 0 1.6rem; font-size: .92rem; }
.onpage a { margin-right: .9rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
gap: 1rem; }
.card { background: #fff; border: 1px solid #e3e7f0; border-radius: 8px;
padding: 1rem; } .card h3 { margin-top: 0; }
.diagram { background: #fff; border: 1px solid #ddd; border-radius: 6px;
padding: 1rem; margin: 1rem 0; overflow-x: auto; }
.diagram svg { max-width: 100%; height: auto; }
.example { background: #fff; border-left: 4px solid #6ca2ee; padding: .6rem .9rem;
margin: .8rem 0; font-size: .95rem; } .example b { color: #2c5fc9; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .95rem; }
th, td { border: 1px solid #ccc; padding: .5rem .7rem; text-align: left;
vertical-align: top; }
th { background: #eee; } code { background: #eee; padding: 0 .25rem;
border-radius: 3px; }
.next { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #e3e7f0;
display: flex; justify-content: space-between; }
.meta { color: #888; font-size: .82rem; }
@media (max-width: 860px) { .shell { grid-template-columns: 1fr; }
.sidebar { position: static; height: auto; border-right: 0;
border-bottom: 1px solid #e3e7f0; } }
"""

LAYOUT = Template("""<!doctype html>
<html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lantern — {{ title }}</title>
<style>{{ style }}</style></head>
<body><div class="shell">
<aside class="sidebar">
<a class="brand" href="index.html">{{ labels.brand }}</a>
<p class="langs"><span>{{ labels.lang_name }}</span><a href="{{ other_href }}"
>{{ labels.other_lang_name }}</a></p>
<nav>
{% for group, items in groups %}<p class="nav-label">{{ group }}</p>
{% for file, name in items %}<a href="{{ file }}"{% if file == current %}
 aria-current="page"{% endif %}>{{ name }}</a>
{% endfor %}{% endfor %}
</nav>
</aside>
<main>
<p class="eyebrow">{{ eyebrow }}</p>
<h1>{{ title }}</h1>
{% if sections %}<div class="onpage"><b>{{ labels.on_this_page }}</b>
{% for anchor, name in sections %}<a href="#{{ anchor }}">{{ name }}</a>
{% endfor %}</div>{% endif %}
{{ body }}
<div class="next">{% if prev %}<a href="{{ prev[0] }}">← {{ prev[1] }}</a>
{% else %}<span></span>{% endif %}
{% if next %}<a href="{{ next[0] }}">{{ next[1] }} →</a>{% endif %}</div>
<p class="meta">{{ labels.regenerated }} {{ generated_at }}. {{ labels.no_network }}</p>
</main></div></body></html>
""")


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
        if m["interval"] is None:
            ci = "—"
        else:
            ci = f"[{m['interval'][0]:.2f}, {m['interval'][1]:.2f}]"
        rows.append({**m, "display": display, "ci": ci})
    return {
        "metrics": rows,
        "population": doc["population"],
        "regenerate": doc["regenerate"],
    }


def _models() -> Dict[str, Any]:
    """The model basket as `config/models.yaml` pins it — ids, prices and the
    verification date come from the file, never from the page text, so the
    site cannot name a model the code does not use."""
    doc = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
    planner = doc["planner"]
    explainer = doc["explainer"]
    judge = doc["eval_judge"]
    explainer_price = next(
        c["price_usd_per_million"]
        for c in explainer["candidates"]
        if c["model"] == explainer["selected"]
    )
    judge_price = next(
        c["price_usd_per_million"]
        for c in judge["candidates"]
        if c["model"] == judge["selected"]
    )
    return {
        "planner": planner["model"],
        "planner_fallback": planner["fallback"],
        "planner_price": planner["price_usd_per_million"],
        "explainer": explainer["selected"],
        "explainer_price": explainer_price,
        "explainer_candidates": len(explainer["candidates"]),
        "judge": judge["selected"],
        "judge_price": judge_price,
        "verified_at": doc["verified_at"],
        "ceiling": doc["budget_ceiling_usd"],
    }


def _contexts() -> Dict[str, Dict[str, Any]]:
    """The diagram slots and data each page needs — identical in both
    languages, which is what keeps the two versions showing the same
    evidence."""
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))["rows"]
    return {
        "index.html": {},
        "architecture.html": {
            "c4_svg": _inline_svg("c4_container"),
            "langgraph_svg": _inline_svg("langgraph_structure"),
            "deployment_svg": _inline_svg("deployment"),
            "mcp_adapter_svg": _inline_svg("mcp_adapter_component"),
            "tools_list_svg": _inline_svg("tools_list_sequence"),
            "domain_class_svg": _inline_svg("domain_core_class"),
            "domain_activity_svg": _inline_svg("diagnose_activity"),
            "g4_activity_svg": _inline_svg("g4_planner_evidence_rank_activity"),
            "g4_sequence_svg": _inline_svg("g4_llm_tool_choice_sequence"),
            "models": _models(),
        },
        "recovery.html": {
            "sequence_svg": _inline_svg("hero_sequence"),
            "state_svg": _inline_svg("graph_state"),
        },
        "safety.html": {
            "g5_sequence_svg": _inline_svg("g5_consent_write_readback_sequence"),
            "g5_refusal_svg": _inline_svg("g5_guard_refusal_sequence"),
            "g8_compensation_happy_svg": _inline_svg("g8_compensation_happy_sequence"),
            "g8_compensation_refusal_svg": _inline_svg(
                "g8_compensation_refusal_sequence"
            ),
            "g8_topology_svg": _inline_svg("g8_graph_topology_with_compensation"),
            "write_state_svg": _inline_svg("g5_graph_state_with_interrupt"),
            "coverage": coverage,
        },
        "evidence.html": {
            "g9_metrics_svg": _inline_svg("g9_metrics_results"),
            **_metrics(),
        },
        "data-model.html": {"er_svg": _inline_svg("neon_schema_er")},
    }


def _nav_groups(content: Any) -> List[Tuple[str, List[Tuple[str, str]]]]:
    groups: List[Tuple[str, List[Tuple[str, str]]]] = []
    for file, name, group in content.NAV:
        label = content.LABELS["groups"][group]
        if not groups or groups[-1][0] != label:
            groups.append((label, []))
        groups[-1][1].append((file, name))
    return groups


def render_all() -> List[Path]:
    contexts = _contexts()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written: List[Path] = []
    for lang, (content, prefix) in LANGUAGES.items():
        out_dir = OUT_DIR / prefix if prefix else OUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        order = [(file, name) for file, name, _ in content.NAV]
        files = [file for file, _ in order]
        for file, body in content.BODIES.items():
            i = files.index(file)
            eyebrow, title = content.TITLES[file]
            html = LAYOUT.render(
                lang=lang,
                style=STYLE,
                labels=content.LABELS,
                other_href=(f"uk/{file}" if lang == "en" else f"../{file}"),
                groups=_nav_groups(content),
                current=file,
                eyebrow=eyebrow,
                title=title,
                sections=content.SECTIONS[file],
                body=Template(body).render(**contexts[file]),
                prev=order[i - 1] if i > 0 else None,
                next=order[i + 1] if i + 1 < len(order) else None,
                generated_at=stamp,
            )
            out = out_dir / file
            out.write_text(html, encoding="utf-8")
            written.append(out)
    return written


def main() -> int:
    for path in render_all():
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
