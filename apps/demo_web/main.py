from __future__ import annotations

import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any
from uuid import uuid4

from caliper_adapters import WebAdapter
from caliper_core.models import OutcomeCreate, OutcomeEvent, ReportGenerateRequest
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
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


class BrowserTelemetryEvent(BaseModel):
    event_type: str
    event_id: str | None = None
    value: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserTelemetryBatch(BaseModel):
    visitor_id: str | None = None
    decision_id: str | None = None
    events: list[BrowserTelemetryEvent] = Field(default_factory=list)


_BROWSER_EVENT_ID_CACHE_SIZE = 5_000
_BROWSER_METRIC_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


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


def _bool_from_query(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_browser_metric(event_type: str) -> str:
    normalized = event_type.strip().lower().replace("-", "_")
    if not _BROWSER_METRIC_PATTERN.fullmatch(normalized):
        raise ValueError(f"Unsupported browser event_type: {event_type!r}")
    return normalized


def _register_browser_event_id(app: FastAPI, event_id: str | None) -> bool:
    if not event_id:
        return True

    cache: set[str] = app.state.browser_event_ids
    order: deque[str] = app.state.browser_event_id_order

    if event_id in cache:
        return False

    if len(order) >= _BROWSER_EVENT_ID_CACHE_SIZE:
        evicted = order.popleft()
        cache.discard(evicted)

    order.append(event_id)
    cache.add(event_id)
    return True


def _browser_tracker_bootstrap_snippet(
    *,
    job_id: str,
    decision_id: str,
    visitor_id: str,
    arm_id: str,
    track_time_spent: bool,
    track_clicks: bool,
) -> str:
    config = {
        "jobId": job_id,
        "decisionId": decision_id,
        "visitorId": visitor_id,
        "armId": arm_id,
        "endpointPath": f"/lp/{job_id}/events",
        "enableAutoTimeSpent": track_time_spent,
        "enableClickTracking": track_clicks,
        "clickSelector": "a[href*='/click'],button[data-caliper-click],[data-caliper-click]",
        "baseMetadata": {
            "path": f"/lp/{job_id}",
            "source": "browser_tracker",
            "surface": "web",
        },
        "timeSpent": {
            "minSeconds": 1.0,
            "measurement": "visible_time",
        },
    }

    config_json = json.dumps(config, separators=(",", ":")).replace("</", "<\\/")
    return (
        "\n<script src='/lp-static/browser_tracker.js' defer></script>"
        "\n<script>(function(){"
        f"const cfg={config_json};"
        "const boot=function(){"
        "const trackerApi=window.CaliperLandingTracker;"
        "if(!trackerApi||typeof trackerApi.bootstrapLandingTelemetry!=='function'){return;}"
        "trackerApi.bootstrapLandingTelemetry(cfg);"
        "};"
        "if(document.readyState==='loading'){"
        "document.addEventListener('DOMContentLoaded',boot,{once:true});"
        "}else{boot();}"
        "})();</script>"
    )


def _augment_variant_html(
    *,
    html_text: str,
    job_id: str,
    decision_id: str,
    visitor_id: str,
    arm_id: str,
    tracker_enabled: bool,
    track_time_spent: bool,
    track_clicks: bool,
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
            + f"<a href='{click_url}' style='{cta_style}' data-caliper-click='cta_primary'>"
            + "Learn more"
            + "</a>"
            + "</div>"
        )

    if "{{CONVERT_URL}}" in html_text:
        html_text = html_text.replace("{{CONVERT_URL}}", convert_url)

    if tracker_enabled:
        snippet = _browser_tracker_bootstrap_snippet(
            job_id=job_id,
            decision_id=decision_id,
            visitor_id=visitor_id,
            arm_id=arm_id,
            track_time_spent=track_time_spent,
            track_clicks=track_clicks,
        )
        if re.search(r"</body>", html_text, flags=re.IGNORECASE):
            html_text = re.sub(
                r"</body>", snippet + "</body>", html_text, count=1, flags=re.IGNORECASE
            )
        else:
            html_text = html_text + snippet

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
    app.state.browser_event_ids = set()
    app.state.browser_event_id_order = deque()

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/lp-static", StaticFiles(directory=str(static_dir)), name="demo_web_static")

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
        tracker_enabled = _bool_from_query(
            request.query_params.get("browser_tracker"),
            default=True,
        )
        track_time_spent = _bool_from_query(
            request.query_params.get("track_time_spent"),
            default=True,
        )
        track_clicks = _bool_from_query(
            request.query_params.get("track_clicks"),
            default=True,
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
            arm_id=assignment.arm_id,
            tracker_enabled=tracker_enabled,
            track_time_spent=track_time_spent,
            track_clicks=track_clicks,
        )

        adapter.log_render(
            unit_id=visitor_id,
            decision_id=assignment.decision_id,
            metadata={
                "path": "/lp/{job_id}",
                "topic": cfg.topic,
                "source": "landing_demo_server",
                "browser_tracker_enabled": tracker_enabled,
                "track_time_spent": track_time_spent,
                "track_clicks": track_clicks,
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

    @app.post("/lp/{job_id}/events")
    def browser_events(
        job_id: str,
        payload: BrowserTelemetryBatch,
        request: Request,
    ) -> JSONResponse:
        if job_id != cfg.job_id:
            raise HTTPException(status_code=404, detail="Unknown landing demo job")

        visitor_id = payload.visitor_id or request.cookies.get("caliper_visitor_id")
        decision_id = payload.decision_id or request.cookies.get("caliper_decision_id")
        if not visitor_id or not decision_id:
            raise HTTPException(status_code=400, detail="Missing visitor or decision context")

        accepted = 0
        ignored_duplicates = 0
        ignored_invalid = 0

        for event in payload.events:
            if not _register_browser_event_id(app, event.event_id):
                ignored_duplicates += 1
                continue

            try:
                metric = _normalize_browser_metric(event.event_type)
            except ValueError:
                ignored_invalid += 1
                continue

            value = max(0.0, float(event.value))
            metadata = {
                **dict(event.metadata),
                "source": "browser_tracker",
                "browser_event_type": metric,
                "event_id": event.event_id,
                "path": f"/lp/{job_id}",
            }

            if metric == "click":
                adapter.log_click(
                    unit_id=visitor_id,
                    decision_id=decision_id,
                    value=value,
                    metadata=metadata,
                )
            elif metric == "conversion":
                adapter.log_conversion(
                    unit_id=visitor_id,
                    decision_id=decision_id,
                    value=value,
                    metadata=metadata,
                )
            else:
                client.log_outcome(
                    OutcomeCreate(
                        workspace_id=cfg.workspace_id,
                        job_id=cfg.job_id,
                        decision_id=decision_id,
                        unit_id=visitor_id,
                        events=[OutcomeEvent(outcome_type=metric, value=value)],
                        metadata=metadata,
                    )
                )
            accepted += 1

        return JSONResponse(
            content={
                "status": "ok",
                "accepted": accepted,
                "ignored_duplicates": ignored_duplicates,
                "ignored_invalid": ignored_invalid,
            }
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
