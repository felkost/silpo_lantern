""" "App starts" against the real Neon instance — migrations run, the
checkpointer's pool opens, and the app still serves `/health` while its
lifespan is live.
"""

import os

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="DATABASE_URL not set"
)


def test_app_starts_against_the_real_neon_instance() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert client.app.state.checkpointer is not None
