from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from caliper_adapters import WebAdapter
from caliper_core.models import ReportGenerateRequest
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field


class DemoWebConfig(BaseModel):
    backend: str = "embedded"
    workspace_id: str
    job_id: str
    topic: str
    variant_manifest: dict[str, str] = Field(default_factory=dict)
    db_url: str | None = None
    api_url: str | None = None
    api_token: str | None = None

    @classmethod
    def load_from_env(cls) -> DemoWebConfig:
        raw_path = Path(
            os.environ.get(
                "CALIPER_DEMO_WEB_CONFIG",
                "reports/landing_page_demo/server_config.json",
            )
        )
        if not raw_path.exists():
            msg = f"Missing demo web config file: {raw_path}"
            raise FileNotFoundError(msg)
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        return cls.model_validate(data)


def _resolve_variant_manifest(config: DemoWebConfig) -> dict[str, Path]:
    manifest: dict[str, Path] = {}
    for arm_id, raw_path in config.variant_manifest.items():
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            msg = f"Variant file missing for arm {arm_id}: {path}"
            raise FileNotFoundError(msg)
        manifest[arm_id] = path
    return manifest


def _build_client(config: DemoWebConfig) -> EmbeddedCaliperClient | ServiceCaliperClient:
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


def _device_from_user_agent(user_agent: str) -> str:
    normalized = user_agent.lower()
    if any(token in normalized for token in ["iphone", "android", "mobile"]):
        return "mobile"
    return "desktop"


def _augment_variant_html(
    *,
    html_text: str,
    job_id: str,
    decision_id: str,
    visitor_id: str,
) -> str:
    click_url = f"/lp/{job_id}/click?decision_id={decision_id}&visitor_id={visitor_id}"
    convert_url = f"/lp/{job_id}/convert?decision_id={decision_id}&visitor_id={visitor_id}"

    if "{{CTA_URL}}" in html_text:
        html_text = html_text.replace("{{CTA_URL}}", click_url)
    else:
        cta_style = (
            "padding:10px 14px;"
            "border-radius:10px;"
            "background:#22d3ee;"
            "color:#0f172a;"
            "text-decoration:none;"
            "font-weight:700"
        )
        html_text = (
            html_text
            + "\n<div style='margin-top:24px'>"
            + f"<a href='{click_url}' style='{cta_style}'>"
            + "Learn more"
            + "</a>"
            + "</div>"
        )

    if "{{CONVERT_URL}}" in html_text:
        html_text = html_text.replace("{{CONVERT_URL}}", convert_url)

    return html_text


def create_app(config: DemoWebConfig | None = None) -> FastAPI:
    cfg = config or DemoWebConfig.load_from_env()
    client = _build_client(cfg)
    adapter = WebAdapter(client=client, workspace_id=cfg.workspace_id, job_id=cfg.job_id)
    variant_manifest = _resolve_variant_manifest(cfg)

    app = FastAPI(title="Caliper landing demo app")
    app.state.config = cfg
    app.state.client = client
    app.state.adapter = adapter
    app.state.variant_manifest = variant_manifest

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "job_id": cfg.job_id}

    @app.get("/lp/{job_id}", response_class=HTMLResponse)
    def render_variant(job_id: str, request: Request) -> HTMLResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        visitor_id = request.query_params.get("visitor_id") or request.cookies.get(
            "caliper_visitor_id"
        )
        if not visitor_id:
            visitor_id = f"visitor-{uuid4().hex[:12]}"

        country = request.query_params.get("country", "US")
        referrer = request.query_params.get("referrer", "direct")
        device = request.query_params.get("device") or _device_from_user_agent(
            request.headers.get("User-Agent", "")
        )

        assignment = adapter.assign_request(
            unit_id=visitor_id,
            idempotency_key=f"landing-live-{cfg.job_id}-{visitor_id}",
            context={"country": country, "device": device, "referrer": referrer},
        )

        variant_path = variant_manifest.get(assignment.arm_id)
        if variant_path is None:
            raise HTTPException(status_code=500, detail=f"Unknown arm payload: {assignment.arm_id}")

        html_text = variant_path.read_text(encoding="utf-8")
        rendered_html = _augment_variant_html(
            html_text=html_text,
            job_id=cfg.job_id,
            decision_id=assignment.decision_id,
            visitor_id=visitor_id,
        )

        adapter.log_render(
            unit_id=visitor_id,
            decision_id=assignment.decision_id,
            metadata={
                "path": "/lp/{job_id}",
                "topic": cfg.topic,
                "source": "landing_demo_server",
            },
        )

        response = HTMLResponse(content=rendered_html)
        response.set_cookie("caliper_visitor_id", visitor_id, path="/")
        response.set_cookie("caliper_decision_id", assignment.decision_id, path="/")
        response.set_cookie("caliper_arm_id", assignment.arm_id, path="/")
        return response

    @app.get("/lp/{job_id}/click")
    def click(job_id: str, request: Request) -> RedirectResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        visitor_id = request.query_params.get("visitor_id") or request.cookies.get(
            "caliper_visitor_id"
        )
        decision_id = request.query_params.get("decision_id") or request.cookies.get(
            "caliper_decision_id"
        )
        if not visitor_id or not decision_id:
            raise HTTPException(status_code=400, detail="Missing visitor or decision context")

        adapter.log_click(
            unit_id=visitor_id,
            decision_id=decision_id,
            metadata={"source": "landing_demo_server"},
        )
        return RedirectResponse(
            url=f"/lp/{job_id}/offer?decision_id={decision_id}&visitor_id={visitor_id}",
            status_code=302,
        )

    @app.get("/lp/{job_id}/offer", response_class=HTMLResponse)
    def offer(job_id: str, request: Request) -> HTMLResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        visitor_id = request.query_params.get("visitor_id") or request.cookies.get(
            "caliper_visitor_id"
        )
        decision_id = request.query_params.get("decision_id") or request.cookies.get(
            "caliper_decision_id"
        )
        if not visitor_id or not decision_id:
            raise HTTPException(status_code=400, detail="Missing visitor or decision context")

        action_url = f"/lp/{job_id}/convert?decision_id={decision_id}&visitor_id={visitor_id}"
        return HTMLResponse(
            content=(
                "<html><body style='font-family:system-ui'>"
                "<h1>Offer page</h1>"
                "<p>You clicked the CTA. Submit to log conversion.</p>"
                f"<form method='post' action='{action_url}'>"
                "<button type='submit'>Complete conversion</button>"
                "</form>"
                f"<p><a href='/lp/{job_id}'>Back to landing page</a></p>"
                "</body></html>"
            )
        )

    @app.api_route("/lp/{job_id}/convert", methods=["GET", "POST"], response_class=HTMLResponse)
    def convert(job_id: str, request: Request) -> HTMLResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        visitor_id = request.query_params.get("visitor_id") or request.cookies.get(
            "caliper_visitor_id"
        )
        decision_id = request.query_params.get("decision_id") or request.cookies.get(
            "caliper_decision_id"
        )
        if not visitor_id or not decision_id:
            raise HTTPException(status_code=400, detail="Missing visitor or decision context")

        adapter.log_conversion(
            unit_id=visitor_id,
            decision_id=decision_id,
            metadata={"source": "landing_demo_server"},
        )

        return HTMLResponse(
            content=(
                "<html><body style='font-family:system-ui'>"
                "<h1>Thanks — conversion logged</h1>"
                f"<p><a href='/lp/{job_id}'>Back to landing page</a></p>"
                "</body></html>"
            )
        )

    @app.get("/lp/{job_id}/report")
    def latest_report(job_id: str) -> JSONResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        report = client.generate_report(
            job_id=cfg.job_id,
            payload=ReportGenerateRequest(workspace_id=cfg.workspace_id),
        )
        return JSONResponse(content=report.model_dump(mode="json"))

    @app.get("/")
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"/lp/{cfg.job_id}", status_code=302)

    return app


def _default_app() -> FastAPI:
    try:
        return create_app()
    except FileNotFoundError:
        app = FastAPI(title="Caliper landing demo app")

        @app.get("/healthz")
        def _healthz() -> dict[str, str]:
            return {
                "status": "error",
                "detail": "CALIPER_DEMO_WEB_CONFIG missing; launch via run_landing_page_demo",
            }

        return app


app = _default_app()
