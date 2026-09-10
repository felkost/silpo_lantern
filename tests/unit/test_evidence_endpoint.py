"""G10 delivery C (claim 5, and claim 1's delivery path): `GET /evidence`
serves the console what a jury may be shown -- each metric with its `n`,
its 95% Wilson interval and its caveat (D81/D82: a proportion without an
interval is a misreading; `SearchPriceFidelity` is not a rate), and the
sanitised disclosure observation (the app's own lines, the codes, which
were rendered) -- never the author's screenshots.

The metrics come from a TRACKED `datasets/golden-v1.0.0/metrics.json`,
regenerated from the tracked bundles by `compute_metrics.py --tracked`;
the script's default output lands in a gitignored directory that does not
exist on Render.
The agreement test regenerates from the bundles and compares, so a
hand-edited or stale tracked file fails the gate on a fresh clone.
"""

import json
import re
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api import routes as routes_module
from scripts.compute_metrics import TRACKED_METRICS_PATH, build_tracked_metrics_report
from src.lantern.domain.metrics import wilson
from tests.unit.test_api_event_enrichment import FORBIDDEN_KEYS, _keys

EXPECTED = {
    "UnauthorizedWriteRate",
    "ReadbackCoverage",
    "ConsentBindingIntegrity",
    "WriteDeltaFidelity",
    "SearchPriceFidelity",
    "RecoveryCompletionRate",
    "FalseRecovery",
    "DisclosureRate",
}


def test_wilson_is_honest_at_the_boundary() -> None:
    # 1 of 1: the interval the handoff quotes, never "100%".
    low, high = wilson(1.0, 1)
    assert round(low, 2) == 0.21 and high == 1.0
    assert wilson(0.0, 0) == (0.0, 0.0)
    low, high = wilson(0.2727272727, 33)
    assert 0.14 < low < 0.16 and 0.43 < high < 0.45


def test_the_tracked_metrics_file_agrees_with_a_regeneration_from_the_bundles() -> None:
    """Runs the 18 offline repeats over the tracked bundles (~3 s) and
    compares everything but the generation timestamp."""
    committed = json.loads(TRACKED_METRICS_PATH.read_text(encoding="utf-8"))
    regenerated = build_tracked_metrics_report()

    committed.pop("generated_at")
    regenerated.pop("generated_at")
    assert committed == regenerated


def test_every_tracked_metric_carries_n_interval_and_caveat() -> None:
    report = json.loads(TRACKED_METRICS_PATH.read_text(encoding="utf-8"))

    assert report["population"] == "offline"
    assert {m["name"] for m in report["metrics"]} == EXPECTED
    for metric in report["metrics"]:
        assert metric["caveat"].strip()
        assert metric["n"] >= 0
        if metric["name"] == "FalseRecovery":
            assert metric["interval"] is None  # a count, not a proportion
        elif metric["value"] is not None:
            assert metric["interval"] == [
                round(x, 4) for x in wilson(metric["value"], metric["n"])
            ]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_module.router)
    return TestClient(app)


def test_evidence_endpoint_serves_metrics_and_the_sanitised_observation() -> None:
    body: Any = _client().get("/evidence").json()

    assert {m["name"] for m in body["metrics"]} == EXPECTED
    assert body["population"] == "offline"
    assert body["regenerate"]  # claim 5: the command beside the numbers
    obs = body["disclosure"]
    assert obs["observed_at"]
    assert any("Мінімальна сума" in line for line in obs["app_showed"])
    codes = {v["code"]: v for v in obs["validations"]}
    assert codes["order.cost.min"]["rendered_by_app"] is True
    assert codes["order.payment_types.disabled"]["rendered_by_app"] is False
    assert set(codes["order.cost.min"]) == {"code", "level", "rendered_by_app"}


def test_evidence_endpoint_carries_no_personal_data() -> None:
    body = _client().get("/evidence").json()

    assert not FORBIDDEN_KEYS & _keys(body)
    text = json.dumps(body, ensure_ascii=False)
    assert "screenshot" not in text.lower()
    # No phone-shaped number: ten or more digits that are not a decimal's tail.
    assert not re.search(r"(?<![\d.])\d{10,}(?![\d.])", text)
