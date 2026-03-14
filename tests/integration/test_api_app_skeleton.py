from __future__ import annotations

import pytest
from api import dependencies
from api.main import create_app
from fastapi.testclient import TestClient


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


def test_health_and_readiness_endpoints_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()
    client = TestClient(create_app())

    health_response = client.get("/healthz")
    ready_response = client.get("/readyz")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}


def test_shared_profile_requires_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "shared")
    monkeypatch.setenv("CALIPER_SHARED_API_TOKEN", "super-secret")
    _reset_dependency_caches()
    client = TestClient(create_app())

    missing = client.get("/v1/system/info")
    invalid = client.get(
        "/v1/system/info",
        headers={"Authorization": "Bearer nope"},
    )
    valid = client.get(
        "/v1/system/info",
        headers={"Authorization": "Bearer super-secret"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json() == {"service": "caliper-api", "api_version": "v1"}
