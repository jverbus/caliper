from __future__ import annotations

import argparse
import json
import os
import random
import smtplib
import socket
import subprocess
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlencode

import httpx
from caliper_adapters import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
    EmailSendInstruction,
    EmailSendPlan,
    EmailTranchePlanner,
    EmailWebhookEvent,
    EmailWebhookType,
)
from caliper_core.models import (
    ArmBulkRegisterRequest,
    ArmInput,
    ArmState,
    ArmType,
    GuardrailAction,
    GuardrailRule,
    GuardrailSpec,
    Job,
    JobStatus,
    ObjectiveSpec,
    PolicyFamily,
    PolicySpec,
    ReportGenerateRequest,
    SurfaceType,
    UpdateCadence,
)
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient
from caliper_storage import build_engine, init_db, make_session_factory
from caliper_storage.sqlalchemy_models import ScheduledTaskRow
from sqlalchemy.orm import Session, sessionmaker

from apps.worker.loop import WorkerLoop

type DemoClient = EmbeddedCaliperClient | ServiceCaliperClient


class DryRunProvider:
    provider_name = "dry-run"

    def deliver(self, plan: EmailSendPlan) -> DeliveryResult:
        now = datetime.now(tz=UTC)
        return DeliveryResult(
            provider=self.provider_name,
            delivered_at=now,
            records=[
                DeliveryRecord(
                    recipient_id=instruction.recipient_id,
                    delivered=True,
                    provider_message_id=f"dry-{plan.tranche_id}-{instruction.recipient_id}",
                )
                for instruction in plan.instructions
            ],
        )


class GmailProvider:
    provider_name = "gmail-smtp"

    def __init__(
        self,
        *,
        username: str,
        app_password: str,
        from_addr: str | None = None,
    ) -> None:
        self.username = username
        self.app_password = app_password
        self.from_addr = from_addr or username

    @classmethod
    def from_env(cls) -> GmailProvider | None:
        user = os.getenv("GMAIL_SMTP_USER")
        password = os.getenv("GMAIL_SMTP_APP_PASSWORD")
        if not user or not password:
            return None
        return cls(username=user, app_password=password, from_addr=os.getenv("GMAIL_SMTP_FROM"))

    def _subject(self, *, instruction: EmailSendInstruction) -> str:
        subject_line = instruction.metadata.get("subject_line")
        if isinstance(subject_line, str) and subject_line.strip():
            return subject_line
        return f"Caliper demo: {instruction.arm_id}"

    def _plain_text(self, *, plan: EmailSendPlan, instruction: EmailSendInstruction) -> str:
        click_url = instruction.metadata.get("tracking_click_url")
        conversion_url = instruction.metadata.get("tracking_conversion_url")
        reply_url = instruction.metadata.get("tracking_reply_url")

        lines = [
            f"Caliper demo send for arm {instruction.arm_id} / tranche {plan.tranche_id}.",
            f"Decision ID: {instruction.decision_id}",
            "",
            "Tracked links:",
        ]

        if isinstance(click_url, str):
            lines.append(f"- Click: {click_url}")
        if isinstance(conversion_url, str):
            lines.append(f"- Conversion: {conversion_url}")
        if isinstance(reply_url, str):
            lines.append(f"- Reply signal ingest (demo route): {reply_url}")

        return "\n".join(lines)

    def _html_body(self, *, plan: EmailSendPlan, instruction: EmailSendInstruction) -> str:
        click_url = instruction.metadata.get("tracking_click_url")
        conversion_url = instruction.metadata.get("tracking_conversion_url")
        reply_url = instruction.metadata.get("tracking_reply_url")

        click_link = (
            f"<li><a href='{click_url}'>Tracked click link</a></li>"
            if isinstance(click_url, str)
            else ""
        )
        conversion_link = (
            f"<li><a href='{conversion_url}'>Tracked conversion link</a></li>"
            if isinstance(conversion_url, str)
            else ""
        )
        reply_link = (
            f"<li><a href='{reply_url}'>Demo reply ingest route</a></li>"
            if isinstance(reply_url, str)
            else ""
        )

        return (
            "<html><body style='font-family:system-ui'>"
            f"<h2>Caliper demo: {instruction.arm_id}</h2>"
            f"<p>Tranche: <code>{plan.tranche_id}</code></p>"
            f"<p>Decision ID: <code>{instruction.decision_id}</code></p>"
            "<ul>"
            f"{click_link}"
            f"{conversion_link}"
            f"{reply_link}"
            "</ul>"
            "</body></html>"
        )

    def deliver(self, plan: EmailSendPlan) -> DeliveryResult:
        now = datetime.now(tz=UTC)
        records: list[DeliveryRecord] = []
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(self.username, self.app_password)
            for instruction in plan.instructions:
                if not instruction.address:
                    records.append(
                        DeliveryRecord(
                            recipient_id=instruction.recipient_id,
                            delivered=False,
                            error="missing recipient email address",
                        )
                    )
                    continue

                message = EmailMessage()
                message["Subject"] = self._subject(instruction=instruction)
                message["From"] = self.from_addr
                message["To"] = instruction.address
                message["X-Caliper-Job-ID"] = plan.job_id
                message["X-Caliper-Tranche-ID"] = plan.tranche_id
                message["X-Caliper-Decision-ID"] = instruction.decision_id
                message["X-Caliper-Recipient-ID"] = instruction.recipient_id
                message.set_content(self._plain_text(plan=plan, instruction=instruction))
                message.add_alternative(
                    self._html_body(plan=plan, instruction=instruction),
                    subtype="html",
                )

                smtp.send_message(message)
                records.append(
                    DeliveryRecord(
                        recipient_id=instruction.recipient_id,
                        delivered=True,
                        provider_message_id=f"gmail-{plan.tranche_id}-{instruction.recipient_id}",
                    )
                )
        return DeliveryResult(provider=self.provider_name, delivered_at=now, records=records)


def _build_client(
    *,
    backend: str,
    db_url: str,
    api_url: str,
    api_token: str | None,
) -> DemoClient:
    if backend == "service":
        return ServiceCaliperClient(api_url=api_url, api_token=api_token)
    if backend == "embedded":
        return EmbeddedCaliperClient(db_url=db_url)
    msg = f"Unsupported backend: {backend!r}"
    raise ValueError(msg)


def _extract_job_id(created: dict[str, Any] | Job) -> str:
    return created["job_id"] if isinstance(created, dict) else created.job_id


def _demo_pythonpath(repo_root: Path) -> str:
    entries = [
        str(repo_root),
        str(repo_root / "packages/py-caliper-core/src"),
        str(repo_root / "packages/py-caliper-storage/src"),
        str(repo_root / "packages/py-caliper-events/src"),
        str(repo_root / "packages/py-caliper-policies/src"),
        str(repo_root / "packages/py-caliper-reward/src"),
        str(repo_root / "packages/py-caliper-reports/src"),
        str(repo_root / "packages/py-caliper-adapters/src"),
        str(repo_root / "packages/py-sdk/src"),
        str(repo_root / "apps"),
    ]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        entries.append(existing)
    return os.pathsep.join(entries)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(*, base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.5)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    msg = f"Email tracking demo server did not become healthy within {timeout_seconds:.1f}s"
    raise RuntimeError(msg)


def _active_arm_ids(client: DemoClient, *, workspace_id: str, job_id: str) -> list[str]:
    arms = client.list_arms(job_id=job_id, workspace_id=workspace_id)
    return sorted([arm.arm_id for arm in arms if arm.state == ArmState.ACTIVE])


def _job_sendable(client: DemoClient, *, job_id: str) -> bool:
    job = client.get_job(job_id=job_id)
    if job is None:
        return False
    return job.status != JobStatus.PAUSED


def _session_factory_for_embedded(db_url: str) -> sessionmaker[Session]:
    engine = build_engine(db_url)
    init_db(engine)
    return make_session_factory(engine)


def _enqueue_due_task(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: str,
    job_id: str,
    task_type: str,
    due_at: datetime,
) -> None:
    with session_factory() as session:
        session.add(
            ScheduledTaskRow(
                workspace_id=workspace_id,
                job_id=job_id,
                task_type=task_type,
                due_at=due_at,
                status="pending",
                payload_json={},
                created_at=due_at,
                updated_at=due_at,
                started_at=None,
                completed_at=None,
                attempt_count=0,
                last_error=None,
            )
        )
        session.commit()


def _tracked_route(
    *,
    tracking_base_url: str,
    route: str,
    decision_id: str,
    recipient_id: str,
    arm_id: str,
    tranche_id: str,
    event_id: str,
) -> str:
    query = urlencode(
        {
            "decision_id": decision_id,
            "recipient_id": recipient_id,
            "arm_id": arm_id,
            "tranche_id": tranche_id,
            "event_id": event_id,
        }
    )
    return f"{tracking_base_url}{route}?{query}"


def _tracking_links(
    *,
    tracking_base_url: str,
    job_id: str,
    decision_id: str,
    recipient_id: str,
    arm_id: str,
    tranche_id: str,
) -> dict[str, str]:
    return {
        "click": _tracked_route(
            tracking_base_url=tracking_base_url,
            route=f"/email/{job_id}/click",
            decision_id=decision_id,
            recipient_id=recipient_id,
            arm_id=arm_id,
            tranche_id=tranche_id,
            event_id=f"click-{decision_id}",
        ),
        "conversion": _tracked_route(
            tracking_base_url=tracking_base_url,
            route=f"/email/{job_id}/convert",
            decision_id=decision_id,
            recipient_id=recipient_id,
            arm_id=arm_id,
            tranche_id=tranche_id,
            event_id=f"conv-{decision_id}",
        ),
        "reply": _tracked_route(
            tracking_base_url=tracking_base_url,
            route=f"/email/{job_id}/reply",
            decision_id=decision_id,
            recipient_id=recipient_id,
            arm_id=arm_id,
            tranche_id=tranche_id,
            event_id=f"reply-{decision_id}",
        ),
    }


def _log_open(
    *,
    adapter: EmailAdapter,
    decision_id: str,
    recipient_id: str,
    topic: str,
    tranche_id: str,
) -> None:
    now = datetime.now(tz=UTC)
    adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id=f"open-{decision_id}",
            webhook_type=EmailWebhookType.OPEN,
            recipient_id=recipient_id,
            decision_id=decision_id,
            occurred_at=now + timedelta(hours=24),
            metadata={
                "topic": topic,
                "tranche_id": tranche_id,
                "source": "email_demo_open_simulation",
            },
        )
    )


def _log_unsubscribe(
    *,
    adapter: EmailAdapter,
    decision_id: str,
    recipient_id: str,
    topic: str,
    tranche_id: str,
) -> None:
    now = datetime.now(tz=UTC)
    adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id=f"unsub-{decision_id}",
            webhook_type=EmailWebhookType.UNSUBSCRIBE,
            recipient_id=recipient_id,
            decision_id=decision_id,
            occurred_at=now + timedelta(hours=2),
            metadata={
                "topic": topic,
                "tranche_id": tranche_id,
                "source": "email_demo_unsubscribe_simulation",
            },
        )
    )


def run_email_demo(
    *,
    topic: str,
    recipients: list[str],
    variant_count: int,
    mode: str,
    backend: str = "embedded",
    db_url: str = "sqlite:///./data/email-orchestrator-demo.db",
    api_url: str = "http://127.0.0.1:8000",
    api_token: str | None = None,
    output_root: str = "reports/email_demo",
    tracking_host: str = "127.0.0.1",
    tracking_port: int = 8876,
    observe_seconds: int = 60,
    simulate_tracked_events: bool | None = None,
) -> dict[str, Any]:
    if variant_count < 2:
        raise ValueError("variant_count must be >= 2")

    workspace_id = "ws-email-orchestrator-demo"
    client = _build_client(
        backend=backend,
        db_url=db_url,
        api_url=api_url,
        api_token=api_token,
    )

    job = Job(
        workspace_id=workspace_id,
        name=f"Email demo: {topic}",
        surface_type=SurfaceType.EMAIL,
        objective_spec=ObjectiveSpec(
            reward_formula="(0.5 * email_open) + (0.8 * email_click) + (2.0 * email_conversion)",
            penalties=["2.0 * email_unsubscribe", "3.0 * email_complaint"],
            secondary_metrics=[
                "email_open",
                "email_click",
                "email_conversion",
                "email_reply",
                "email_unsubscribe",
            ],
        ),
        guardrail_spec=GuardrailSpec(
            rules=[
                GuardrailRule(
                    metric="email_unsubscribe",
                    op=">",
                    threshold=0.08,
                    action=GuardrailAction.CAP,
                )
            ]
        ),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            params={
                "seed": 77,
                "alpha": {f"subject-{i}": 10.0 + i for i in range(variant_count)},
                "beta": {f"subject-{i}": 10.0 + (variant_count - i) for i in range(variant_count)},
            },
            update_cadence=UpdateCadence(mode="periodic", seconds=300),
        ),
    )
    created = client.create_job(job)
    job_id = _extract_job_id(created)

    arms = [
        ArmInput(
            arm_id=f"subject-{i}",
            name=f"Subject Variant {i + 1}",
            arm_type=ArmType.ARTIFACT,
            payload_ref=f"email://subject-{i}",
            metadata={"topic": topic, "subject_line": f"{topic}: Variant {i + 1}"},
        )
        for i in range(variant_count)
    ]
    subject_line_by_arm = {
        arm.arm_id: str(arm.metadata.get("subject_line", f"Caliper demo: {arm.arm_id}"))
        for arm in arms
    }
    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(workspace_id=workspace_id, arms=arms),
    )

    adapter = EmailAdapter(client=client, workspace_id=workspace_id, job_id=job_id)
    planner = EmailTranchePlanner(
        adapter=adapter,
        active_arm_supplier=lambda: _active_arm_ids(
            client,
            workspace_id=workspace_id,
            job_id=job_id,
        ),
        can_send_supplier=lambda: _job_sendable(client, job_id=job_id),
    )

    if mode == "live":
        gmail_provider = GmailProvider.from_env()
        if gmail_provider is None:
            msg = (
                "Live mode requires Gmail SMTP credentials. Set GMAIL_SMTP_USER and "
                "GMAIL_SMTP_APP_PASSWORD (and optionally GMAIL_SMTP_FROM)."
            )
            raise ValueError(msg)
        provider: DryRunProvider | GmailProvider = gmail_provider
        provider_mode = "gmail"
    else:
        provider = DryRunProvider()
        provider_mode = "dry-run-seam"

    synthetic_driver_enabled = (
        mode == "dry_run" if simulate_tracked_events is None else simulate_tracked_events
    )

    session_factory: sessionmaker[Session] | None = None
    policy_update_mode = "external_worker_expected"
    if backend == "embedded":
        session_factory = _session_factory_for_embedded(db_url)
        policy_update_mode = "inline_worker_loop"

    assignment_counts: dict[str, int] = {f"subject-{i}": 0 for i in range(variant_count)}
    active_arms_by_tranche: dict[str, list[str]] = {}
    synthetic_event_counts: dict[str, int] = {
        "email_open": 0,
        "email_click": 0,
        "email_conversion": 0,
        "email_reply": 0,
        "email_unsubscribe": 0,
    }
    dispatch_manifest: list[dict[str, Any]] = []
    policy_update_runs = 0

    recipient_rows = [
        {"recipient_id": f"r-{idx:03d}", "address": addr}
        for idx, addr in enumerate(recipients, start=1)
    ]
    tranche_size = max(1, len(recipient_rows) // 2)
    tranches = [recipient_rows[:tranche_size], recipient_rows[tranche_size:]]

    output_dir = Path(output_root) / mode
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved_tracking_port = _free_port() if tracking_port == 0 else tracking_port
    tracking_base_url = f"http://{tracking_host}:{resolved_tracking_port}"
    report_url = f"{tracking_base_url}/email/{job_id}/report"
    tracking_routes = {
        "click": f"{tracking_base_url}/email/{job_id}/click",
        "conversion": f"{tracking_base_url}/email/{job_id}/convert",
        "reply": f"{tracking_base_url}/email/{job_id}/reply",
    }

    tracking_config_path = output_dir / "tracking_server_config.json"
    tracking_config_path.write_text(
        json.dumps(
            {
                "backend": backend,
                "workspace_id": workspace_id,
                "job_id": job_id,
                "topic": topic,
                "db_url": db_url,
                "api_url": api_url,
                "api_token": api_token,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    tracking_log_path = output_dir / "tracking_server.log"
    tracking_process: subprocess.Popen[Any] | None = None
    log_handle: TextIO | None = None

    rng = random.Random(99)

    try:
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["CALIPER_DEMO_EMAIL_CONFIG"] = str(tracking_config_path.resolve())
        env["PYTHONPATH"] = _demo_pythonpath(repo_root)

        log_handle = tracking_log_path.open("w", encoding="utf-8")
        tracking_process = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "apps.demo_email.main:app",
                "--host",
                tracking_host,
                "--port",
                str(resolved_tracking_port),
            ],
            cwd=str(repo_root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        _wait_for_server(base_url=tracking_base_url)

        with httpx.Client(timeout=10.0, follow_redirects=False) as tracking_client:
            for tranche_index, tranche_recipients in enumerate(tranches, start=1):
                if not tranche_recipients:
                    continue

                tranche_id = f"tranche-{tranche_index}"
                active_arms_by_tranche[tranche_id] = _active_arm_ids(
                    client,
                    workspace_id=workspace_id,
                    job_id=job_id,
                )

                plan = planner.plan_next_tranche(
                    tranche_id=tranche_id,
                    recipients=[
                        EmailRecipient(
                            recipient_id=row["recipient_id"],
                            address=row["address"],
                        )
                        for row in tranche_recipients
                    ],
                    idempotency_prefix=f"email-{mode}-{backend}-{job_id}",
                    campaign_context={"topic": topic, "tranche": tranche_index},
                )

                links_by_decision: dict[str, dict[str, str]] = {}
                for item in plan.instructions:
                    assignment_counts[item.arm_id] += 1
                    links = _tracking_links(
                        tracking_base_url=tracking_base_url,
                        job_id=job_id,
                        decision_id=item.decision_id,
                        recipient_id=item.recipient_id,
                        arm_id=item.arm_id,
                        tranche_id=tranche_id,
                    )
                    links_by_decision[item.decision_id] = links
                    item.metadata.update(
                        {
                            "topic": topic,
                            "subject_line": subject_line_by_arm.get(
                                item.arm_id,
                                f"Caliper demo: {item.arm_id}",
                            ),
                            "tracking_click_url": links["click"],
                            "tracking_conversion_url": links["conversion"],
                            "tracking_reply_url": links["reply"],
                        }
                    )

                delivery = adapter.dispatch_send_plan(plan=plan, provider=provider)
                records_by_recipient = {record.recipient_id: record for record in delivery.records}

                for item in plan.instructions:
                    record = records_by_recipient.get(item.recipient_id)
                    links = links_by_decision[item.decision_id]
                    dispatch_manifest.append(
                        {
                            "tranche_id": tranche_id,
                            "recipient_id": item.recipient_id,
                            "recipient_address": item.address,
                            "arm_id": item.arm_id,
                            "decision_id": item.decision_id,
                            "subject_line": subject_line_by_arm.get(item.arm_id),
                            "provider": delivery.provider,
                            "provider_message_id": (
                                record.provider_message_id if record is not None else None
                            ),
                            "delivered": record.delivered if record is not None else False,
                            "tracking": links,
                        }
                    )

                if synthetic_driver_enabled:
                    for item in plan.instructions:
                        _log_open(
                            adapter=adapter,
                            decision_id=item.decision_id,
                            recipient_id=item.recipient_id,
                            topic=topic,
                            tranche_id=tranche_id,
                        )
                        synthetic_event_counts["email_open"] += 1

                        links = links_by_decision[item.decision_id]
                        if rng.random() < 0.45:
                            click_response = tracking_client.get(links["click"])
                            if click_response.status_code >= 400:
                                click_response.raise_for_status()
                            synthetic_event_counts["email_click"] += 1

                            if rng.random() < 0.2:
                                conversion_response = tracking_client.post(links["conversion"])
                                if conversion_response.status_code >= 400:
                                    conversion_response.raise_for_status()
                                synthetic_event_counts["email_conversion"] += 1

                        if item.arm_id.endswith("0") and rng.random() < 0.35:
                            _log_unsubscribe(
                                adapter=adapter,
                                decision_id=item.decision_id,
                                recipient_id=item.recipient_id,
                                topic=topic,
                                tranche_id=tranche_id,
                            )
                            synthetic_event_counts["email_unsubscribe"] += 1

                        if rng.random() < 0.08:
                            reply_response = tracking_client.post(links["reply"])
                            if reply_response.status_code >= 400:
                                reply_response.raise_for_status()
                            synthetic_event_counts["email_reply"] += 1

                if session_factory is not None:
                    _enqueue_due_task(
                        session_factory,
                        workspace_id=workspace_id,
                        job_id=job_id,
                        task_type="run_policy_update",
                        due_at=datetime.now(tz=UTC) - timedelta(minutes=1),
                    )
                    WorkerLoop(session_factory).run_once(max_due_tasks=10)
                    policy_update_runs += 1

            if mode == "live" and not synthetic_driver_enabled and observe_seconds > 0:
                time.sleep(observe_seconds)

            report = client.generate_report(
                job_id=job_id,
                payload=ReportGenerateRequest(workspace_id=workspace_id),
            )
            report_dict = report.model_dump(mode="json")
    finally:
        if tracking_process is not None:
            tracking_process.terminate()
            try:
                tracking_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tracking_process.kill()
                tracking_process.wait(timeout=3)
        if log_handle is not None:
            log_handle.close()

    leaders = report_dict.get("leaders", [])
    winner = leaders[0]["arm_id"] if leaders else "unknown"

    dispatch_manifest_path = output_dir / "dispatch_manifest.json"
    dispatch_manifest_path.write_text(
        json.dumps(dispatch_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    reply_ingest_command = (
        "uv run python scripts/ingest_email_reply_signal.py "
        f"--backend {backend} --workspace-id {workspace_id} --job-id {job_id} "
        "--recipient-id <recipient_id> --decision-id <decision_id>"
    )
    if backend == "embedded":
        reply_ingest_command += f" --db-url {db_url}"
    else:
        reply_ingest_command += f" --api-url {api_url}"
        if api_token:
            reply_ingest_command += " --api-token <api_token>"

    summary = {
        "manifest_version": "demo-orchestrator-email-v2",
        "surface": "email",
        "topic": topic,
        "mode": mode,
        "backend": backend,
        "provider_mode": provider_mode,
        "variant_count": variant_count,
        "recipient_count": len(recipients),
        "winner_arm_id": winner,
        "assignment_counts": assignment_counts,
        "active_arms_by_tranche": active_arms_by_tranche,
        "report_id": report_dict["report_id"],
        "job_id": report_dict["job_id"],
        "urls": {
            "tracking_base_url": tracking_base_url,
            "tracking_routes": tracking_routes,
            "report_url": report_url,
        },
        "measurement": {
            "click_conversion_ingest": "tracked_http_routes",
            "reply_ingest": "tracked_http_route_or_manual_command",
            "open_ingest": (
                "synthetic_webhook_simulation"
                if synthetic_driver_enabled
                else "external_signals_or_none"
            ),
            "synthetic_driver_enabled": synthetic_driver_enabled,
            "synthetic_event_counts": synthetic_event_counts,
            "reply_ingest_command": reply_ingest_command,
        },
        "metrics": {
            "reward_formula": job.objective_spec.reward_formula,
            "secondary_metrics": job.objective_spec.secondary_metrics,
            "leaders": leaders,
        },
        "policy_update": {
            "mode": policy_update_mode,
            "runs": policy_update_runs,
        },
        "artifacts": {
            "report_json": str(output_dir / "report.json"),
            "report_md": str(output_dir / "report.md"),
            "report_html": str(output_dir / "report.html"),
            "winner_summary_json": str(output_dir / "winner_summary.json"),
            "dispatch_manifest_json": str(dispatch_manifest_path),
            "tracking_server_config": str(tracking_config_path),
            "tracking_server_log": str(tracking_log_path),
        },
    }

    (output_dir / "report.json").write_text(
        json.dumps(report_dict, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(report_dict["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report_dict["html"], encoding="utf-8")
    (output_dir / "winner_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run email demo orchestration")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--recipients", required=True, help="Comma-separated recipient emails")
    parser.add_argument("--variant-count", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=["dry_run", "live"],
        default="dry_run",
        help=(
            "dry_run = synthetic provider + tracked endpoint driver; "
            "live = real Gmail SMTP send path (fails fast if credentials are missing)"
        ),
    )
    parser.add_argument("--backend", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/email-orchestrator-demo.db")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--output-root", default="reports/email_demo")
    parser.add_argument("--tracking-host", default="127.0.0.1")
    parser.add_argument("--tracking-port", type=int, default=8876)
    parser.add_argument(
        "--observe-seconds",
        type=int,
        default=60,
        help=(
            "For live mode with no synthetic tracked-event driver, keep the tracking server "
            "running for this many seconds before report generation"
        ),
    )
    parser.add_argument(
        "--simulate-tracked-events",
        action="store_true",
        help="Force synthetic click/conversion/reply route hits (enabled by default in dry_run)",
    )
    parser.add_argument(
        "--no-simulate-tracked-events",
        action="store_true",
        help="Disable synthetic tracked-event route hits",
    )
    args = parser.parse_args()

    recipients = [value.strip() for value in args.recipients.split(",") if value.strip()]
    if not recipients:
        raise ValueError("at least one recipient is required")

    if args.simulate_tracked_events and args.no_simulate_tracked_events:
        raise ValueError(
            "choose at most one of --simulate-tracked-events or --no-simulate-tracked-events"
        )

    simulate_flag: bool | None = None
    if args.simulate_tracked_events:
        simulate_flag = True
    elif args.no_simulate_tracked_events:
        simulate_flag = False

    summary = run_email_demo(
        topic=args.topic,
        recipients=recipients,
        variant_count=args.variant_count,
        mode=args.mode,
        backend=args.backend,
        db_url=args.db_url,
        api_url=args.api_url,
        api_token=args.api_token,
        output_root=args.output_root,
        tracking_host=args.tracking_host,
        tracking_port=args.tracking_port,
        observe_seconds=args.observe_seconds,
        simulate_tracked_events=simulate_flag,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
