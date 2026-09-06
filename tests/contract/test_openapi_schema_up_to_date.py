"""OpenAPI 3.1 is generated from the route definitions (`app.openapi()`,
confirmed live: FastAPI 0.141.1 emits `"openapi": "3.1.0"` by default),
never hand-authored separately — this test is the guard against the "two
schemas that drift" trap the committed `apps/api/openapi.json` would
otherwise fall into silently.
"""

import json

from src.lantern.config import PROJECT_ROOT
from apps.api.main import app


def test_committed_openapi_json_matches_the_live_generated_schema() -> None:
    committed = json.loads(
        (PROJECT_ROOT / "apps" / "api" / "openapi.json").read_text(encoding="utf-8")
    )
    assert committed == app.openapi()
