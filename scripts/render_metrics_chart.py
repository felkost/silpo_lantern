"""G9 (G9.9): the stage's one declared diagram -- a results chart of the
seven metrics with 95% Wilson intervals, generated from the metrics
report `compute_metrics.py` writes rather than drawn by hand.

Generated, not authored, because the numbers move every time the evidence
is recomputed and a hand-drawn chart silently goes stale. A metric with
`n == 0` is rendered as an explicit N/A row, never as a zero bar -- the
same rule the metrics themselves follow.

Wilson rather than normal-approximation intervals: at n=33 with a
proportion of exactly 1.00 the normal interval collapses to a point, which
would draw four of the gates as though they had been measured with
infinite confidence. Wilson stays honest at the boundary.

Follows this project's diagram conventions: Arial only, injected into the
SVG's own <defs> (the standalone-SVG font trap), nothing below 12px, all
text English in ink #24242E, no sixth colour.
"""

from __future__ import annotations

import json
import math
from typing import Callable, Dict, List, Tuple

from src.lantern.config import PROJECT_ROOT

METRICS_PATH = PROJECT_ROOT / "docs" / "evidence" / "metrics.json"
OUT_PATH = PROJECT_ROOT / "docs" / "uml" / "svg" / "g9_metrics_results.svg"

INK = "#24242E"
MUTED = "#6B7280"
HAIRLINE = "#D1D5DB"
# Domain/Safety fill: every one of these metrics is a property of the
# domain and safety layers, so the palette's own rule -- colour by what the
# block IS -- puts them in one colour rather than inventing an accent for
# "the good ones".
BAR_FILL = "#9A85E1"
BAR_STROKE = "#6440C9"
GATE_MET = "#2C5FC9"

ROW_HEIGHT = 42
LEFT = 250
BAR_LEFT = LEFT + 10
BAR_WIDTH = 440
TOP = 108

# Each metric's gate as plan section 13.3 states it.
GATES: Dict[str, Tuple[str, Callable[[float], bool]]] = {
    "UnauthorizedWriteRate": ("0.00 absolute", lambda v: v == 0.0),
    "ReadbackCoverage": ("1.00", lambda v: v == 1.0),
    "ConsentBindingIntegrity": ("1.00", lambda v: v == 1.0),
    "WriteDeltaFidelity": ("1.00 absolute", lambda v: v == 1.0),
    "SearchPriceFidelity": ("no gate - observation", lambda v: True),
    "RecoveryCompletionRate": ("0.85 core", lambda v: v >= 0.85),
    "FalseRecovery": ("0 absolute", lambda v: v == 0.0),
    "DisclosureRate": ("measured", lambda v: True),
}
# FalseRecovery is a COUNT, not a proportion -- it gets no interval.
COUNT_METRICS = {"FalseRecovery"}


def wilson(p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(metrics: List[dict]) -> str:
    height = TOP + ROW_HEIGHT * len(metrics) + 80
    width = 1000
    parts: List[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">' % (width, height, width, height)
    )
    # The font trap: a standalone SVG cannot borrow the page's CSS.
    parts.append(
        "<defs><style>text{font-family:Arial,Helvetica,"
        '"Liberation Sans","DejaVu Sans",sans-serif;}</style></defs>'
    )
    parts.append('<rect width="%d" height="%d" fill="#FFFFFF"/>' % (width, height))
    parts.append(
        '<text x="24" y="34" font-size="14" font-weight="700" fill="%s">'
        "G9 measurement results - seven metrics, 95%% Wilson intervals</text>" % INK
    )
    parts.append(
        '<text x="24" y="58" font-size="12" fill="%s">Computed by '
        "scripts/compute_metrics.py from the offline repeats own emitted run "
        "records (D61: reproducible from the repository, which a live LLM run "
        "is not).</text>" % MUTED
    )
    parts.append(
        '<text x="24" y="78" font-size="12" fill="%s">n is the population each '
        "metric was measured over. A metric with n = 0 is N/A, never a zero "
        "bar.</text>" % MUTED
    )

    axis_bottom = TOP + ROW_HEIGHT * len(metrics) - 8
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = BAR_LEFT + tick * BAR_WIDTH
        parts.append(
            '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"/>'
            % (x, TOP - 12, x, axis_bottom, HAIRLINE)
        )
        parts.append(
            '<text x="%.1f" y="%d" font-size="12" fill="%s" text-anchor="middle">'
            "%.2f</text>" % (x, TOP - 18, MUTED, tick)
        )

    for index, metric in enumerate(metrics):
        name = metric["name"]
        value = metric["value"]
        n = metric["n"]
        y = TOP + index * ROW_HEIGHT
        centre = y + 18
        gate_text, gate_ok = GATES.get(name, ("-", lambda v: True))

        parts.append(
            '<text x="24" y="%d" font-size="12" font-weight="700" fill="%s">%s</text>'
            % (centre, INK, _esc(name))
        )
        parts.append(
            '<text x="%d" y="%d" font-size="12" fill="%s" text-anchor="end">'
            "n = %d</text>" % (LEFT - 50, centre, MUTED, n)
        )

        if value is None:
            parts.append(
                '<text x="%d" y="%d" font-size="12" fill="%s">N/A - no verified '
                "population</text>" % (BAR_LEFT, centre, MUTED)
            )
        elif name in COUNT_METRICS:
            parts.append(
                '<text x="%d" y="%d" font-size="12" font-weight="700" fill="%s">'
                "%d false claim(s) across %d receipts - a count, not a rate</text>"
                % (BAR_LEFT, centre, INK, int(value), n)
            )
        else:
            fill = GATE_MET if gate_ok(value) else BAR_FILL
            parts.append(
                '<rect x="%d" y="%d" width="%.1f" height="20" fill="%s" '
                'stroke="%s"/>' % (BAR_LEFT, y + 8, value * BAR_WIDTH, fill, BAR_STROKE)
            )
            low, high = wilson(value, n)
            x1 = BAR_LEFT + low * BAR_WIDTH
            x2 = BAR_LEFT + high * BAR_WIDTH
            mid = y + 18
            parts.append(
                '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" '
                'stroke-width="1.5"/>' % (x1, mid, x2, mid, INK)
            )
            for cap in (x1, x2):
                parts.append(
                    '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" '
                    'stroke-width="1.5"/>' % (cap, mid - 6, cap, mid + 6, INK)
                )
            parts.append(
                '<text x="%d" y="%d" font-size="12" font-weight="700" fill="%s">'
                "%.2f</text>" % (BAR_LEFT + BAR_WIDTH + 12, centre, INK, value)
            )

        parts.append(
            '<text x="%d" y="%d" font-size="12" fill="%s">gate: %s</text>'
            % (BAR_LEFT + BAR_WIDTH + 62, centre, MUTED, _esc(gate_text))
        )

    legend_y = TOP + ROW_HEIGHT * len(metrics) + 26
    parts.append(
        '<rect x="24" y="%d" width="16" height="14" fill="%s" stroke="%s"/>'
        % (legend_y - 11, GATE_MET, BAR_STROKE)
    )
    parts.append(
        '<text x="48" y="%d" font-size="12" fill="%s">gate met</text>' % (legend_y, INK)
    )
    parts.append(
        '<rect x="132" y="%d" width="16" height="14" fill="%s" stroke="%s"/>'
        % (legend_y - 11, BAR_FILL, BAR_STROKE)
    )
    parts.append(
        '<text x="156" y="%d" font-size="12" fill="%s">gate not met - reported, '
        "not relaxed</text>" % (legend_y, INK)
    )
    parts.append(
        '<text x="24" y="%d" font-size="12" fill="%s">SearchPriceFidelity carries no '
        "gate: it measures how well the product search predicts the price the "
        "cart charges, which is Silpo policy (D68, D76), not this system.</text>"
        % (legend_y + 24, MUTED)
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))["metrics"]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(build_svg(metrics), encoding="utf-8")
    print("wrote %s" % OUT_PATH.relative_to(PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
