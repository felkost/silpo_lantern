""" "App starts" is verified through `GET /health`, not `docker compose up`
(no Dockerfile exists yet). Liveness only — no I/O — so this stays a free,
offline contract test in `make gate`, never reaching Neon or the live MCP
server.
"""

from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_returns_200_with_no_network_or_database_access() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
