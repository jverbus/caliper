from __future__ import annotations

import argparse
import json
import os
import random
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from caliper_adapters import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
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
from caliper_sdk import EmbeddedCaliperClient
from caliper_storage import SQLRepository, build_engine, init_db, make_session_factory
from caliper_storage.sqlalchemy_models import ScheduledTaskRow
from sqlalchemy.orm import Session, sessionmaker

from apps.worker.loop import WorkerLoop


class DryRunProvider:
    provider_name = "dry-run"

    def deliver(self, plan: Any) -> DeliveryResult:
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

    def __init__(self, *, username: str, app_password: str, from_addr: str | None = None) -> None:
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

    def deliver(self, plan: Any) -> DeliveryResult:
        now = datetime.now(tz=UTC)
        records: list[DeliveryRecord] = []
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(self.username, self.app_password)
            for instruction in plan.instructions:
                message = EmailMessage()
                message["Subject"] = f"Caliper demo: {instruction.arm_id}"
                message["From"] = self.from_addr
                message["To"] = instruction.recipient_address
                message.set_content(
                    f"Demo send for arm {instruction.arm_id} / tranche {plan.tranche_id}."
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


def _repository(db_url: str) -> tuple[SQLRepository, sessionmaker[Session]]:
    engine = build_engine(db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    return SQLRepository(session_factory), session_factory


def _active_arm_ids(repository: SQLRepository, *, workspace_id: str, job_id: str) -> list[str]:
    arms = repository.list_arms(workspace_id=workspace_id, job_id=job_id)
    return sorted([arm.arm_id for arm in arms if arm.state == ArmState.ACTIVE])


def _job_sendable(repository: SQLRepository, *, job_id: str) -> bool:
    job = repository.get_job(job_id)
    return bool(job is not None and job.status != JobStatus.PAUSED)


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


def run_email_demo(
    *,
    topic: str,
    recipients: list[str],
    variant_count: int,
    mode: str,
    db_url: str = "sqlite:///./data/email-orchestrator-demo.db",
    output_root: str = "reports/email_demo",
) -> dict[str, Any]:
    if variant_count < 2:
        raise ValueError("variant_count must be >= 2")

    workspace_id = "ws-email-orchestrator-demo"
    client = EmbeddedCaliperClient(db_url=db_url)
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
                # Thompson engine consumes per-arm alpha/beta priors.
                "alpha": {f"subject-{i}": 10.0 + i for i in range(variant_count)},
                "beta": {f"subject-{i}": 10.0 + (variant_count - i) for i in range(variant_count)},
            },
            update_cadence=UpdateCadence(mode="periodic", seconds=300),
        ),
    )
    created = client.create_job(job)
    job_id = created["job_id"] if isinstance(created, dict) else created.job_id

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
    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(workspace_id=workspace_id, arms=arms),
    )

    repository, session_factory = _repository(db_url=db_url)
    adapter = EmailAdapter(client=client, workspace_id=workspace_id, job_id=job_id)
    planner = EmailTranchePlanner(
        adapter=adapter,
        active_arm_supplier=lambda: _active_arm_ids(
            repository, workspace_id=workspace_id, job_id=job_id
        ),
        can_send_supplier=lambda: _job_sendable(repository, job_id=job_id),
    )

    if mode == "live":
        gmail_provider = GmailProvider.from_env()
        if gmail_provider is None:
            msg = (
                "Live mode requires Gmail SMTP credentials. Set GMAIL_SMTP_USER and "
                "GMAIL_SMTP_APP_PASSWORD (and optionally GMAIL_SMTP_FROM)."
            )
            raise ValueError(msg)
        provider: Any = gmail_provider
        provider_mode = "gmail"
    else:
        provider = DryRunProvider()
        provider_mode = "dry-run-seam"

    assignment_counts: dict[str, int] = {f"subject-{i}": 0 for i in range(variant_count)}
    active_arms_by_tranche: dict[str, list[str]] = {}

    rng = random.Random(99)
    tranche_size = max(1, len(recipients) // 2)
    tranches = [recipients[:tranche_size], recipients[tranche_size:]]

    for tranche_index, tranche_recipients in enumerate(tranches, start=1):
        if not tranche_recipients:
            continue
        tranche_id = f"tranche-{tranche_index}"
        active_arms_by_tranche[tranche_id] = _active_arm_ids(
            repository, workspace_id=workspace_id, job_id=job_id
        )

        plan = planner.plan_next_tranche(
            tranche_id=tranche_id,
            recipients=[
                EmailRecipient(recipient_id=f"r-{idx}", address=addr)
                for idx, addr in enumerate(tranche_recipients, start=1)
            ],
            idempotency_prefix=f"email-{mode}-{job_id}",
            campaign_context={"topic": topic, "tranche": tranche_index},
        )
        for item in plan.instructions:
            assignment_counts[item.arm_id] += 1

        adapter.dispatch_send_plan(plan=plan, provider=provider)

        now = datetime.now(tz=UTC)
        for item in plan.instructions:
            adapter.ingest_webhook(
                event=EmailWebhookEvent(
                    webhook_event_id=f"open-{item.decision_id}",
                    webhook_type=EmailWebhookType.OPEN,
                    recipient_id=item.recipient_id,
                    decision_id=item.decision_id,
                    occurred_at=now + timedelta(hours=24),
                    metadata={"topic": topic},
                )
            )
            if rng.random() < 0.45:
                adapter.ingest_webhook(
                    event=EmailWebhookEvent(
                        webhook_event_id=f"click-{item.decision_id}",
                        webhook_type=EmailWebhookType.CLICK,
                        recipient_id=item.recipient_id,
                        decision_id=item.decision_id,
                        occurred_at=now + timedelta(hours=25),
                        metadata={"topic": topic},
                    )
                )
            if rng.random() < 0.2:
                adapter.ingest_webhook(
                    event=EmailWebhookEvent(
                        webhook_event_id=f"conv-{item.decision_id}",
                        webhook_type=EmailWebhookType.CONVERSION,
                        recipient_id=item.recipient_id,
                        decision_id=item.decision_id,
                        occurred_at=now + timedelta(hours=26),
                        metadata={"topic": topic},
                    )
                )
            if item.arm_id.endswith("0") and rng.random() < 0.35:
                adapter.ingest_webhook(
                    event=EmailWebhookEvent(
                        webhook_event_id=f"unsub-{item.decision_id}",
                        webhook_type=EmailWebhookType.UNSUBSCRIBE,
                        recipient_id=item.recipient_id,
                        decision_id=item.decision_id,
                        occurred_at=now + timedelta(hours=2),
                        metadata={"topic": topic},
                    )
                )

        _enqueue_due_task(
            session_factory,
            workspace_id=workspace_id,
            job_id=job_id,
            task_type="run_policy_update",
            due_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )
        WorkerLoop(session_factory).run_once(max_due_tasks=10)

    report = client.generate_report(
        job_id=job_id,
        payload=ReportGenerateRequest(workspace_id=workspace_id),
    )
    report_dict = report.model_dump(mode="json")
    leaders = report_dict.get("leaders", [])
    winner = leaders[0]["arm_id"] if leaders else "unknown"

    output_dir = Path(output_root) / mode
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "topic": topic,
        "mode": mode,
        "variant_count": variant_count,
        "recipient_count": len(recipients),
        "winner_arm_id": winner,
        "assignment_counts": assignment_counts,
        "provider_mode": provider_mode,
        "report_id": report_dict["report_id"],
        "job_id": report_dict["job_id"],
        "active_arms_by_tranche": active_arms_by_tranche,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report_dict, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(report_dict["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report_dict["html"], encoding="utf-8")
    (output_dir / "winner_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
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
            "dry_run = synthetic provider/events; "
            "live = real Gmail SMTP send path (fails fast if credentials are missing)"
        ),
    )
    parser.add_argument("--db-url", default="sqlite:///./data/email-orchestrator-demo.db")
    parser.add_argument("--output-root", default="reports/email_demo")
    args = parser.parse_args()

    recipients = [value.strip() for value in args.recipients.split(",") if value.strip()]
    if not recipients:
        raise ValueError("at least one recipient is required")

    summary = run_email_demo(
        topic=args.topic,
        recipients=recipients,
        variant_count=args.variant_count,
        mode=args.mode,
        db_url=args.db_url,
        output_root=args.output_root,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
