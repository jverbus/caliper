from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
import typer

app = typer.Typer(help="Caliper CLI")


def _parse_json(value: str, *, field_name: str) -> dict[str, Any] | list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:  # pragma: no cover - handled by tests
        raise typer.BadParameter(f"Invalid JSON for {field_name}: {exc}") from exc
    if not isinstance(parsed, (dict, list)):
        raise typer.BadParameter(f"{field_name} must decode to a JSON object or array")
    return parsed


def _request(
    *,
    method: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
    api_url: str,
    api_token: str | None,
) -> dict[str, Any] | list[Any]:
    headers: dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    with httpx.Client(base_url=api_url, timeout=30.0, headers=headers) as client:
        response = client.request(method, path, json=payload)

    if response.status_code >= 400:
        detail: str
        try:
            body = response.json()
            detail = json.dumps(body, indent=2, sort_keys=True)
        except ValueError:
            detail = response.text
        typer.echo(f"Request failed ({response.status_code}): {detail}", err=True)
        raise typer.Exit(code=1)

    parsed = response.json()
    if not isinstance(parsed, (dict, list)):
        typer.echo("Unexpected non-JSON response.", err=True)
        raise typer.Exit(code=1)
    return parsed


def _emit(result: dict[str, Any] | list[Any]) -> None:
    typer.echo(json.dumps(result, indent=2, sort_keys=True, default=str))


@app.command("create-job")
def create_job(
    workspace_id: str = typer.Option(..., help="Workspace identifier."),
    name: str = typer.Option(..., help="Human-readable job name."),
    surface_type: str = typer.Option("web", help="Surface type (web/email/workflow)."),
    objective_spec: str = typer.Option(..., help="Objective spec JSON object."),
    guardrail_spec: str = typer.Option(..., help="Guardrail spec JSON object."),
    policy_spec: str = typer.Option(..., help="Policy spec JSON object."),
    segment_spec: str = typer.Option('{"dimensions": []}', help="Segment spec JSON object."),
    schedule_spec: str = typer.Option('{"report_cron": null}', help="Schedule spec JSON object."),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload = {
        "workspace_id": workspace_id,
        "name": name,
        "surface_type": surface_type,
        "objective_spec": _parse_json(objective_spec, field_name="objective_spec"),
        "guardrail_spec": _parse_json(guardrail_spec, field_name="guardrail_spec"),
        "policy_spec": _parse_json(policy_spec, field_name="policy_spec"),
        "segment_spec": _parse_json(segment_spec, field_name="segment_spec"),
        "schedule_spec": _parse_json(schedule_spec, field_name="schedule_spec"),
    }
    _emit(
        _request(
            method="POST",
            path="/v1/jobs",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("add-arms")
def add_arms(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    arms: str = typer.Option(..., help="JSON array of arm objects."),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload = {
        "workspace_id": workspace_id,
        "arms": _parse_json(arms, field_name="arms"),
    }
    _emit(
        _request(
            method="POST",
            path=f"/v1/jobs/{job_id}/arms:batch_register",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("assign")
def assign(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    unit_id: str = typer.Option(...),
    idempotency_key: str = typer.Option(...),
    candidate_arms: str | None = typer.Option(None, help="Optional JSON array of arm ids."),
    context: str = typer.Option("{}", help="JSON object context payload."),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload: dict[str, Any] = {
        "workspace_id": workspace_id,
        "job_id": job_id,
        "unit_id": unit_id,
        "idempotency_key": idempotency_key,
        "context": _parse_json(context, field_name="context"),
    }
    if candidate_arms is not None:
        payload["candidate_arms"] = _parse_json(candidate_arms, field_name="candidate_arms")

    _emit(
        _request(
            method="POST",
            path="/v1/assign",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("log-exposure")
def log_exposure(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    decision_id: str = typer.Option(...),
    unit_id: str = typer.Option(...),
    exposure_type: str = typer.Option("rendered"),
    metadata: str = typer.Option("{}", help="Optional JSON object metadata."),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload = {
        "workspace_id": workspace_id,
        "job_id": job_id,
        "decision_id": decision_id,
        "unit_id": unit_id,
        "exposure_type": exposure_type,
        "metadata": _parse_json(metadata, field_name="metadata"),
    }
    _emit(
        _request(
            method="POST",
            path="/v1/exposures",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("log-outcome")
def log_outcome(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    decision_id: str = typer.Option(...),
    unit_id: str = typer.Option(...),
    events: str = typer.Option(..., help="JSON array of outcome event objects."),
    attribution_window: str = typer.Option('{"hours": 24}', help="JSON attribution window."),
    metadata: str = typer.Option("{}", help="Optional JSON object metadata."),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload = {
        "workspace_id": workspace_id,
        "job_id": job_id,
        "decision_id": decision_id,
        "unit_id": unit_id,
        "events": _parse_json(events, field_name="events"),
        "attribution_window": _parse_json(attribution_window, field_name="attribution_window"),
        "metadata": _parse_json(metadata, field_name="metadata"),
    }
    _emit(
        _request(
            method="POST",
            path="/v1/outcomes",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("generate-report")
def generate_report(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload = {"workspace_id": workspace_id}
    _emit(
        _request(
            method="POST",
            path=f"/v1/jobs/{job_id}/reports:generate",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("pause-job")
def pause_job(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    approval_state: str | None = typer.Option(None),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload: dict[str, Any] = {"workspace_id": workspace_id}
    if approval_state is not None:
        payload["approval_state"] = approval_state
    _emit(
        _request(
            method="POST",
            path=f"/v1/jobs/{job_id}/pause",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


@app.command("resume-job")
def resume_job(
    workspace_id: str = typer.Option(...),
    job_id: str = typer.Option(...),
    approval_state: str | None = typer.Option(None),
    api_url: str = typer.Option("http://127.0.0.1:8000", envvar="CALIPER_API_URL"),
    api_token: str | None = typer.Option(None, envvar="CALIPER_API_TOKEN"),
) -> None:
    payload: dict[str, Any] = {"workspace_id": workspace_id}
    if approval_state is not None:
        payload["approval_state"] = approval_state
    _emit(
        _request(
            method="POST",
            path=f"/v1/jobs/{job_id}/resume",
            payload=payload,
            api_url=api_url,
            api_token=api_token,
        )
    )


if __name__ == "__main__":
    app()
