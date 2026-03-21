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
    ("params", "expected_recommendation"),
    [
        ({"guardrail_regression": "true"}, "ROLLBACK"),
        ({}, "HOLD"),
        ({"guardrail_delta": "-0.08", "max_guardrail_drop": "0.05"}, "ROLLBACK"),
    ],
)
def test_decision_summary_endpoint_returns_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, str],
    expected_recommendation: str,
) -> None:
    monkeypatch.setenv("CALIPER_PROFILE", "embedded")
    _reset_dependency_caches()

    client = TestClient(create_app())

    response = client.get("/decision/summary", params=params)

    assert response.status_code == 200
    assert response.json() == {"recommendation": expected_recommendation}
