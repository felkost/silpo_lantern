"""Three gate tests one design note declared , each
guarding an artefact that is easy to let drift because nothing executes it.

The first restores the brief's actual guarantee -- the state machine is
exported FROM the code, and CI fails when the committed copy no longer
matches. The export lives under `tests/unit/fixtures/` rather than beside
the rendered diagrams, because the generated-documentation tree is
gitignored and a guarantee that lives only in an ignored file is not a
guarantee.
"""

import re
from datetime import datetime, timezone

import pytest

from src.lantern.config import PROJECT_ROOT
from src.lantern.graph.build import build_recovery_graph
from src.lantern.policies.loader import load_registry

MERMAID_EXPORT = PROJECT_ROOT / "tests" / "unit" / "fixtures" / "graph_topology.mermaid"
FIXTURES_ROOT = PROJECT_ROOT / "datasets" / "fixtures"
# Built from parts, and named the way `scripts/render_report.py` names it:
# the rendered-diagram tree is gitignored, so a tracked file must not spell
# its path out as a literal (`test_tracked_files_reference_tracked_files`).
SVG_ROOT = PROJECT_ROOT / "docs" / "uml" / "svg"
RENDER_REPORT = PROJECT_ROOT / "scripts" / "render_report.py"


def _topology() -> str:
    """The compiled graph's own mermaid rendering. The injected callables
    are never invoked -- only the node/edge wiring is being read -- so
    trivial stubs are enough and no fixture data is needed."""
    graph = build_recovery_graph(
        fetch_my_cart=lambda: {},
        fetch_cart_by_id=lambda cart_id: {},
        registry=load_registry(),
        fetch_delivery_types=lambda lat, lon: {},
        fetch_time_slots=lambda branch_id, types: {},
        fetch_find_products_batch=lambda *args, **kwargs: {},
        planner_call=lambda state: None,
        explainer_call=lambda proposal: None,
        now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return str(graph.get_graph().draw_mermaid())


def test_t21_exported_graph_matches_the_committed_copy() -> None:
    """A topology change that nobody re-exported fails here rather than
    silently making every diagram of the graph wrong."""
    assert MERMAID_EXPORT.read_text(encoding="utf-8") == _topology(), (
        "The graph's topology changed. Re-export it with:\n"
        '  python -c "from tests.unit.test_declared_stage_artifacts import'
        " _topology; open(r'%s', 'w', encoding='utf-8').write(_topology())\""
        % MERMAID_EXPORT
    )


def test_t21b_the_export_carries_the_write_path_and_its_interrupt() -> None:
    """Pins the two properties the diagrams and the project's invariants
    depend on: the write segment exists, and the guard is the interrupted
    node -- not merely that some export file is present."""
    topology = _topology()
    assert "write_guard" in topology
    assert "__interrupt = before" in topology
    assert "write_and_readback --> persist_receipt" in topology
    # The second consent+write round is part of the topology, not an
    # application-level retry loop outside the graph.
    assert "persist_receipt" in topology and "retry" in topology


def test_t22_every_fixture_file_appears_in_the_manifest() -> None:
    """`scripts/sanitize_fixture.py` never registers what it writes, so a
    fixture can exist, be used by tests, and be invisible to the manifest
    that is supposed to describe the dataset."""
    manifest = (FIXTURES_ROOT / "manifest.json").read_text(encoding="utf-8")

    # `raw/` is deliberately outside this check: it holds unsanitized live
    # captures carrying a real delivery address, is gitignored for exactly
    # that reason, and the manifest's own `$comment` scopes it to the
    # sanitized/synthetic/mutated sets.
    described = ("sanitized", "synthetic", "mutated")
    missing = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for directory in described
        for path in sorted((FIXTURES_ROOT / directory).glob("*.json"))
        if path.stem not in manifest
    ]

    assert missing == [], f"fixtures absent from manifest.json: {missing}"


@pytest.mark.skipif(
    not SVG_ROOT.exists(),
    reason="the rendered-diagram tree is gitignored; a fresh clone has none",
)
def test_t24_every_report_diagram_slot_resolves_to_a_rendered_svg() -> None:
    """`render_report.py` fills each slot by name. A diagram that was drawn
    but never copied into the rendered-diagram tree, or a slot whose name was typed
    slightly differently, renders as nothing at all -- silently, since the
    template simply interpolates an empty string."""
    names = re.findall(r'_inline_svg\("([^"]+)"\)', RENDER_REPORT.read_text("utf-8"))
    assert names, "no _inline_svg slots found -- has render_report.py changed shape?"

    missing = [name for name in names if not (SVG_ROOT / f"{name}.svg").exists()]

    assert missing == [], f"report slots with no rendered SVG: {missing}"
