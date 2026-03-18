from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from caliper_adapters import EmailAdapter, EmailWebhookEvent, EmailWebhookType
from caliper_core.models import ReportGenerateRequest
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel


class DemoEmailConfig(BaseModel):
    backend: str = "embedded"
    workspace_id: str
    job_id: str
    topic: str
    db_url: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    default_redirect_url: str = "https://example.com/caliper-demo"

    @classmethod
    def load_from_env(cls) -> DemoEmailConfig:
        raw_path = Path(
            os.environ.get(
                "CALIPER_DEMO_EMAIL_CONFIG",
                "reports/email_demo/server_config.json",
            )
        )
        if not raw_path.exists():
            msg = f"Missing demo email config file: {raw_path}"
            raise FileNotFoundError(msg)
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        return cls.model_validate(data)


def _build_client(config: DemoEmailConfig) -> EmbeddedCaliperClient | ServiceCaliperClient:
    if config.backend == "service":
        if not config.api_url:
            msg = "service backend requires api_url"
            raise ValueError(msg)
        return ServiceCaliperClient(api_url=config.api_url, api_token=config.api_token)

    if config.backend != "embedded":
        msg = f"Unsupported backend: {config.backend!r}"
        raise ValueError(msg)
    if not config.db_url:
        msg = "embedded backend requires db_url"
        raise ValueError(msg)
    return EmbeddedCaliperClient(db_url=config.db_url)


def _required_query(request: Request, *, key: str) -> str:
    value = request.query_params.get(key)
    if value:
        return value
    raise HTTPException(status_code=400, detail=f"Missing required query param: {key}")


def _parse_timestamp(raw_timestamp: str | None) -> datetime:
    if not raw_timestamp:
        return datetime.now(tz=UTC)
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _build_webhook_event(
    *,
    cfg: DemoEmailConfig,
    request: Request,
    webhook_type: EmailWebhookType,
) -> EmailWebhookEvent:
    decision_id = _required_query(request, key="decision_id")
    recipient_id = _required_query(request, key="recipient_id")

    occurred_at = _parse_timestamp(request.query_params.get("occurred_at"))
    webhook_event_id = request.query_params.get("event_id")
    if not webhook_event_id:
        webhook_event_id = f"{webhook_type.value}-{decision_id}-{recipient_id}"

    metadata: dict[str, str | int | float | bool] = {
        "source": "email_demo_tracking_server",
        "topic": cfg.topic,
    }
    arm_id = request.query_params.get("arm_id")
    if arm_id:
        metadata["arm_id"] = arm_id
    tranche_id = request.query_params.get("tranche_id")
    if tranche_id:
        metadata["tranche_id"] = tranche_id

    return EmailWebhookEvent(
        webhook_event_id=webhook_event_id,
        webhook_type=webhook_type,
        recipient_id=recipient_id,
        decision_id=decision_id,
        occurred_at=occurred_at,
        metadata=metadata,
    )


def create_app(config: DemoEmailConfig | None = None) -> FastAPI:
    cfg = config or DemoEmailConfig.load_from_env()
    client = _build_client(cfg)
    adapter = EmailAdapter(client=client, workspace_id=cfg.workspace_id, job_id=cfg.job_id)

    app = FastAPI(title="Caliper email tracking demo app")
    app.state.config = cfg
    app.state.client = client
    app.state.adapter = adapter

    def _ensure_job(job_id: str) -> None:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown email demo job")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "job_id": cfg.job_id}

    @app.get("/email/{job_id}/click")
    def click(job_id: str, request: Request) -> RedirectResponse:
        _ensure_job(job_id)

        event = _build_webhook_event(cfg=cfg, request=request, webhook_type=EmailWebhookType.CLICK)
        adapter.ingest_webhook(event=event)

        next_url = request.query_params.get("next")
        if next_url:
            return RedirectResponse(url=next_url, status_code=302)

        offer_url = (
            f"/email/{job_id}/offer?decision_id={event.decision_id}"
            f"&recipient_id={event.recipient_id}"
        )
        return RedirectResponse(url=offer_url, status_code=302)

    @app.get("/email/{job_id}/offer", response_class=HTMLResponse)
    def offer(job_id: str, request: Request) -> HTMLResponse:
        _ensure_job(job_id)

        decision_id = _required_query(request, key="decision_id")
        recipient_id = _required_query(request, key="recipient_id")
        conversion_event_id = f"conv-{decision_id}-{recipient_id}"

        convert_url = (
            f"/email/{job_id}/convert?decision_id={decision_id}"
            f"&recipient_id={recipient_id}"
            f"&event_id={conversion_event_id}"
        )
        return HTMLResponse(
            content=(
                "<html><body style='font-family:system-ui'>"
                "<h1>Email offer page</h1>"
                "<p>Clicking this button logs a conversion outcome.</p>"
                f"<form method='post' action='{convert_url}'>"
                "<button type='submit'>Complete conversion</button>"
                "</form>"
                "</body></html>"
            )
        )

    @app.api_route(
        "/email/{job_id}/convert",
        methods=["GET", "POST"],
        response_class=HTMLResponse,
    )
    def convert(job_id: str, request: Request) -> HTMLResponse:
        _ensure_job(job_id)

        event = _build_webhook_event(
            cfg=cfg,
            request=request,
            webhook_type=EmailWebhookType.CONVERSION,
        )
        adapter.ingest_webhook(event=event)

        return HTMLResponse(
            content=(
                "<html><body style='font-family:system-ui'>"
                "<h1>Thanks — conversion logged</h1>"
                f"<p>Decision: <code>{event.decision_id}</code></p>"
                f"<p>Recipient: <code>{event.recipient_id}</code></p>"
                "</body></html>"
            )
        )

    @app.api_route("/email/{job_id}/reply", methods=["GET", "POST"])
    def reply(job_id: str, request: Request) -> JSONResponse:
        _ensure_job(job_id)

        event = _build_webhook_event(cfg=cfg, request=request, webhook_type=EmailWebhookType.REPLY)
        outcome = adapter.ingest_webhook(event=event)
        return JSONResponse(
            content={
                "status": "duplicate" if outcome is None else "ingested",
                "job_id": cfg.job_id,
                "decision_id": event.decision_id,
                "recipient_id": event.recipient_id,
                "event_id": event.webhook_event_id,
                "metric": "email_reply",
            }
        )

    @app.get("/email/{job_id}/report")
    def latest_report(job_id: str) -> JSONResponse:
        _ensure_job(job_id)

        report = client.generate_report(
            job_id=cfg.job_id,
            payload=ReportGenerateRequest(workspace_id=cfg.workspace_id),
        )
        return JSONResponse(content=report.model_dump(mode="json"))

    @app.get("/")
    def root() -> RedirectResponse:
        synthetic_decision = f"demo-{uuid4().hex[:10]}"
        synthetic_recipient = "demo-recipient"
        url = (
            f"/email/{cfg.job_id}/offer?decision_id={synthetic_decision}"
            f"&recipient_id={synthetic_recipient}"
        )
        return RedirectResponse(url=url, status_code=302)

    return app


def _default_app() -> FastAPI:
    try:
        return create_app()
    except FileNotFoundError:
        app = FastAPI(title="Caliper email tracking demo app")

        @app.get("/healthz")
        def _healthz() -> dict[str, str]:
            return {
                "status": "error",
                "detail": "CALIPER_DEMO_EMAIL_CONFIG missing; launch via run_email_demo",
            }

        return app


app = _default_app()
