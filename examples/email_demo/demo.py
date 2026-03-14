from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
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
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient
from caliper_storage import SQLRepository, build_engine, init_db, make_session_factory
from caliper_storage.sqlalchemy_models import ScheduledTaskRow
from sqlalchemy.orm import Session, sessionmaker
from worker.loop import WorkerLoop

type DemoClient = EmbeddedCaliperClient | ServiceCaliperClient


class DemoDeliveryProvider:
    provider_name = "demo-smtp"

    def deliver(self, plan: Any) -> DeliveryResult:
        delivered_at = datetime.now(tz=UTC)
        return DeliveryResult(
            provider=self.provider_name,
            delivered_at=delivered_at,
            records=[
                DeliveryRecord(
                    recipient_id=item.recipient_id,
                    delivered=True,
                    provider_message_id=f"msg-{plan.tranche_id}-{item.recipient_id}",
                )
                for item in plan.instructions
            ],
        )


def _sqlite_db_path(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None

    sqlite_path = db_url.removeprefix("sqlite:///")
    if not sqlite_path or sqlite_path == ":memory:":
        return None

    db_file = Path(sqlite_path)
    if not db_file.is_absolute():
        db_file = Path.cwd() / db_file
    return db_file


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    db_file = _sqlite_db_path(db_url)
    if db_file is None:
        return
    db_file.parent.mkdir(parents=True, exist_ok=True)


def _reset_sqlite_file(db_url: str) -> None:
    db_file = _sqlite_db_path(db_url)
    if db_file is None:
        return
    if db_file.exists():
        db_file.unlink()


def _build_demo_job(*, workspace_id: str, name: str) -> Job:
    return Job(
        workspace_id=workspace_id,
        name=name,
        surface_type=SurfaceType.EMAIL,
        objective_spec=ObjectiveSpec(
            reward_formula="(0.6 * email_click) + (2.5 * email_conversion)",
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
                    threshold=0.01,
                    action=GuardrailAction.CAP,
                )
            ]
        ),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.THOMPSON_SAMPLING,
            params={
                "arms": {
                    "subject-a": {"successes": 14, "failures": 12},
                    "subject-b": {"successes": 12, "failures": 14},
                },
                "seed": 11,
            },
            update_cadence=UpdateCadence(mode="periodic", seconds=300),
        ),
    )


def _demo_client(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> DemoClient:
    if mode == "embedded":
        _ensure_sqlite_parent_dir(db_url)
        return EmbeddedCaliperClient(db_url=db_url)
    return ServiceCaliperClient(api_url=api_url, api_token=api_token)


def _repository(db_url: str) -> tuple[SQLRepository, sessionmaker[Session]]:
    _ensure_sqlite_parent_dir(db_url)
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


def _log_outcomes_for_tranche(
    *,
    adapter: EmailAdapter,
    plan: Any,
    tranche_index: int,
    delayed_events: list[str],
) -> None:
    now = datetime.now(tz=UTC)
    for idx, instruction in enumerate(plan.instructions, start=1):
        delayed_open_at = now + timedelta(hours=24 + tranche_index)
        adapter.ingest_webhook(
            event=EmailWebhookEvent(
                webhook_event_id=f"open-{instruction.decision_id}",
                webhook_type=EmailWebhookType.OPEN,
                recipient_id=instruction.recipient_id,
                decision_id=instruction.decision_id,
                occurred_at=delayed_open_at,
                metadata={"tranche": tranche_index},
            )
        )
        delayed_events.append(instruction.decision_id)

        if instruction.arm_id == "subject-b" and idx % 2 == 1:
            adapter.ingest_webhook(
                event=EmailWebhookEvent(
                    webhook_event_id=f"unsub-{instruction.decision_id}",
                    webhook_type=EmailWebhookType.UNSUBSCRIBE,
                    recipient_id=instruction.recipient_id,
                    decision_id=instruction.decision_id,
                    occurred_at=now + timedelta(hours=12),
                    metadata={"reason": "fatigue", "tranche": tranche_index},
                )
            )
            continue

        adapter.ingest_webhook(
            event=EmailWebhookEvent(
                webhook_event_id=f"click-{instruction.decision_id}",
                webhook_type=EmailWebhookType.CLICK,
                recipient_id=instruction.recipient_id,
                decision_id=instruction.decision_id,
                occurred_at=now + timedelta(hours=2),
                metadata={"tranche": tranche_index},
            )
        )
        if instruction.arm_id == "subject-a":
            adapter.ingest_webhook(
                event=EmailWebhookEvent(
                    webhook_event_id=f"conv-{instruction.decision_id}",
                    webhook_type=EmailWebhookType.CONVERSION,
                    recipient_id=instruction.recipient_id,
                    decision_id=instruction.decision_id,
                    occurred_at=now + timedelta(hours=28),
                    metadata={"tranche": tranche_index},
                )
            )


def run_demo(*, mode: str, db_url: str, api_url: str, api_token: str | None) -> dict[str, Any]:
    workspace_id = "ws-email-demo"
    if mode == "embedded":
        _reset_sqlite_file(db_url)

    client = _demo_client(mode=mode, db_url=db_url, api_url=api_url, api_token=api_token)
    created = client.create_job(
        _build_demo_job(workspace_id=workspace_id, name=f"Email demo ({mode})")
    )
    job_id = created["job_id"] if isinstance(created, dict) else created.job_id

    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(
            workspace_id=workspace_id,
            arms=[
                ArmInput(
                    arm_id="subject-a",
                    name="Subject line A",
                    arm_type=ArmType.ARTIFACT,
                    payload_ref="email://subject-a",
                    metadata={"tone": "benefit-led"},
                ),
                ArmInput(
                    arm_id="subject-b",
                    name="Subject line B",
                    arm_type=ArmType.ARTIFACT,
                    payload_ref="email://subject-b",
                    metadata={"tone": "urgency-led"},
                ),
            ],
        ),
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
    provider = DemoDeliveryProvider()

    assignment_counts: dict[str, int] = {"subject-a": 0, "subject-b": 0}
    active_arms_by_tranche: dict[str, list[str]] = {}
    delayed_events: list[str] = []

    tranche_recipients = [
        [
            EmailRecipient(recipient_id=f"t1-r{i:02d}", address=f"t1-r{i:02d}@demo.test")
            for i in range(1, 7)
        ],
        [
            EmailRecipient(recipient_id=f"t2-r{i:02d}", address=f"t2-r{i:02d}@demo.test")
            for i in range(1, 5)
        ],
    ]

    for tranche_index, recipients in enumerate(tranche_recipients, start=1):
        tranche_id = f"tranche-{tranche_index}"
        active_arms = _active_arm_ids(repository, workspace_id=workspace_id, job_id=job_id)
        active_arms_by_tranche[tranche_id] = active_arms

        plan = planner.plan_next_tranche(
            tranche_id=tranche_id,
            recipients=recipients,
            idempotency_prefix=f"email-{mode}",
            campaign_context={"campaign": "spring-launch", "tranche": tranche_index},
        )
        for instruction in plan.instructions:
            assignment_counts[instruction.arm_id] += 1

        adapter.dispatch_send_plan(plan=plan, provider=provider)
        _log_outcomes_for_tranche(
            adapter=adapter,
            plan=plan,
            tranche_index=tranche_index,
            delayed_events=delayed_events,
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
    report_dict["assignment_counts"] = assignment_counts
    report_dict["active_arms_by_tranche"] = active_arms_by_tranche
    report_dict["delayed_outcome_decisions"] = len(delayed_events)
    return report_dict


def _write_artifacts(*, report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(report["markdown"], encoding="utf-8")
    (output_dir / "report.html").write_text(report["html"], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Caliper email demo")
    parser.add_argument("--mode", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/email-demo.db")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    report = run_demo(
        mode=args.mode,
        db_url=args.db_url,
        api_url=args.api_url,
        api_token=args.api_token,
    )
    output_dir = Path(args.output_dir or f"docs/fixtures/email_demo/{args.mode}")
    _write_artifacts(report=report, output_dir=output_dir)

    print(f"email demo complete ({args.mode})")
    print(f"report_id={report['report_id']} assignments={report['assignment_counts']}")
    print(f"artifacts={output_dir}")


if __name__ == "__main__":
    main()
