"""the built SPA is served from `/` without
shadowing the API. Built against a `tmp_path` dist, never the repo's own
`apps/web/dist/` -- that directory is gitignored, so a test importing
`apps.api.main.app` in a fresh clone would see no mount at all and pass
without proving anything.
"""

from pathlib import Path
from typing import Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.main import mount_web


def _app_with_dist(dist: Path) -> FastAPI:
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<h1>Ліхтарик</h1>", encoding="utf-8")
    app = FastAPI()

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/session")
    def session() -> Dict[str, str]:
        return {"session_id": "s1"}

    assert mount_web(app, dist) is True
    return app


def test_root_serves_index_and_earlier_routes_still_resolve(tmp_path: Path) -> None:
    client = TestClient(_app_with_dist(tmp_path / "dist"))

    assert client.get("/").status_code == 200
    assert "Ліхтарик" in client.get("/").text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/session").json() == {"session_id": "s1"}


def test_post_to_an_unrouted_path_is_405_with_the_mount(tmp_path: Path) -> None:
    """Recorded, not prevented (by design): a root mount answers every path,
    so an unknown POST is now a method mismatch, not a missing route."""
    client = TestClient(_app_with_dist(tmp_path / "dist"))

    assert client.post("/nope").status_code == 405


def test_a_missing_dist_is_skipped_not_fatal(tmp_path: Path) -> None:
    """`StaticFiles` raises `RuntimeError` on a missing directory (measured,
    by design) -- a fresh clone with no `npm run build` must still start."""
    app = FastAPI()

    assert mount_web(app, tmp_path / "absent") is False
    assert TestClient(app).get("/").status_code == 404
