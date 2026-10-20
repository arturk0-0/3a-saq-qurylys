"""Unit tests may use MockTransport, but never contact a real paid provider."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Use an explicit test HTTP adapter; external HTTP is forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
