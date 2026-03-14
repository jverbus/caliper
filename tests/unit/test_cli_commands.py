from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest
from cli.main import app
from typer.testing import CliRunner


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | list[Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any] | list[Any]:
        return self._body


class _FakeClient:
    requests: ClassVar[
        list[tuple[str, str, dict[str, Any] | None, dict[str, str], str]]
    ] = []

    def __init__(self, *, base_url: str, timeout: float, headers: dict[str, str]) -> None:
        self._base_url = base_url
        self._headers = headers
        self._responses: dict[tuple[str, str], _FakeResponse] = {
            ("POST", "/v1/jobs"): _FakeResponse(200, {"job_id": "job_1", "status": "draft"}),
            ("POST", "/v1/jobs/job_1/arms:batch_register"): _FakeResponse(
                200,
                {"registered_count": 1},
            ),
            ("POST", "/v1/assign"): _FakeResponse(200, {"decision_id": "dec_1", "arm_id": "arm-a"}),
            ("POST", "/v1/exposures"): _FakeResponse(200, {"decision_id": "dec_1"}),
            ("POST", "/v1/outcomes"): _FakeResponse(200, {"decision_id": "dec_1"}),
            ("POST", "/v1/jobs/job_1/reports:generate"): _FakeResponse(200, {"report_id": "rpt_1"}),
            ("POST", "/v1/jobs/job_1/pause"): _FakeResponse(200, {"status": "paused"}),
            ("POST", "/v1/jobs/job_1/resume"): _FakeResponse(200, {"status": "active"}),
        }

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> _FakeResponse:
        self.requests.append((method, path, json, self._headers, self._base_url))
        return self._responses[(method, path)]


def test_cli_core_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.requests.clear()
    monkeypatch.setattr("cli.main.httpx.Client", _FakeClient)
    runner = CliRunner()

    create = runner.invoke(
        app,
        [
            "create-job",
            "--workspace-id",
            "ws-demo",
            "--name",
            "Demo",
            "--objective-spec",
            '{"reward_formula": "signup"}',
            "--guardrail-spec",
            '{"rules": []}',
            "--policy-spec",
            '{"policy_family": "fixed_split", "params": {"weights": {"arm-a": 1.0}}}',
        ],
    )
    assert create.exit_code == 0
    assert '"job_id": "job_1"' in create.stdout

    add_arms = runner.invoke(
        app,
        [
            "add-arms",
            "--workspace-id",
            "ws-demo",
            "--job-id",
            "job_1",
            "--arms",
            '[{"arm_id":"arm-a","name":"A","arm_type":"artifact","payload_ref":"file://a","metadata":{}}]',
        ],
    )
    assert add_arms.exit_code == 0

    assign = runner.invoke(
        app,
        [
            "assign",
            "--workspace-id",
            "ws-demo",
            "--job-id",
            "job_1",
            "--unit-id",
            "user-1",
            "--idempotency-key",
            "req-1",
            "--candidate-arms",
            '["arm-a"]',
        ],
    )
    assert assign.exit_code == 0
    assert '"arm_id": "arm-a"' in assign.stdout

    exposure = runner.invoke(
        app,
        [
            "log-exposure",
            "--workspace-id",
            "ws-demo",
            "--job-id",
            "job_1",
            "--decision-id",
            "dec_1",
            "--unit-id",
            "user-1",
        ],
    )
    assert exposure.exit_code == 0

    outcome = runner.invoke(
        app,
        [
            "log-outcome",
            "--workspace-id",
            "ws-demo",
            "--job-id",
            "job_1",
            "--decision-id",
            "dec_1",
            "--unit-id",
            "user-1",
            "--events",
            '[{"outcome_type":"signup","value":1.0}]',
        ],
    )
    assert outcome.exit_code == 0

    report = runner.invoke(
        app,
        ["generate-report", "--workspace-id", "ws-demo", "--job-id", "job_1"],
    )
    assert report.exit_code == 0

    pause = runner.invoke(app, ["pause-job", "--workspace-id", "ws-demo", "--job-id", "job_1"])
    assert pause.exit_code == 0

    resume = runner.invoke(app, ["resume-job", "--workspace-id", "ws-demo", "--job-id", "job_1"])
    assert resume.exit_code == 0

    assert len(_FakeClient.requests) == 8
    method, path, _, _, _ = _FakeClient.requests[0]
    assert method == "POST"
    assert path == "/v1/jobs"
