from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api import dependencies
from apps.api.main import create_app


def _reset_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies._cached_engine.cache_clear()
    dependencies._cached_session_factory.cache_clear()


@pytest.mark.parametrize(
    ("guardrail_regression", "expected_recommendation"),
    [
        ("true", "ROLLBACK"),
        (None, "HOLD"),
    ],
)
def test_decision_summary_endpoint_returns_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
    guardrail_regression: str | None,
    expected_recommendation: str,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()

    client = TestClient(create_app())

    params = {}
    if guardrail_regression is not None:
        params["guardrail_regression"] = guardrail_regression
    response = client.get("/decision/summary", params=params)

    assert response.status_code == 200
    assert response.json() == {"recommendation": expected_recommendation}
