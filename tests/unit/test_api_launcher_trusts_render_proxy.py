"""G10 (D89): behind Render's proxy `request.client.host` is the proxy
itself unless uvicorn trusts `X-Forwarded-For` -- and then the per-IP
session cap would be one shared cap for every guest. The launcher trusts
the proxy only when `$PORT` is set (Render's own convention, the same
signal `__main__` already uses to bind `0.0.0.0`).
"""

from typing import Any, Dict

import pytest
import uvicorn

from apps.api import __main__ as launcher


def _captured_config(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    def fake_config(app: str, **kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    class _Server:
        def __init__(self, config: object) -> None:
            pass

        def run(self) -> None:
            pass

        async def serve(self) -> None:
            pass

    monkeypatch.setattr(uvicorn, "Config", fake_config)
    monkeypatch.setattr(uvicorn, "Server", _Server)
    launcher.main()
    return captured


def test_render_port_set_means_trust_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "10000")

    assert _captured_config(monkeypatch)["forwarded_allow_ips"] == "*"


def test_local_dev_trusts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT", raising=False)

    assert "forwarded_allow_ips" not in _captured_config(monkeypatch)
