from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from caliper_adapters import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
    EmailSendPlan,
    EmailTranchePlanner,
    EmailWebhookEvent,
    EmailWebhookType,
    TranchePlanningBlockedError,
)
from caliper_core.models import (
    AssignResult,
    DecisionDiagnostics,
    ExposureCreate,
    OutcomeCreate,
    PolicyFamily,
)


class _FakeEmailClient:
    def __init__(self) -> None:
        self.assign_payloads: list[Any] = []
        self.exposures: list[ExposureCreate] = []
        self.outcomes: list[OutcomeCreate] = []

    def assign(self, payload: Any) -> AssignResult:
        self.assign_payloads.append(payload)
        return AssignResult(
            decision_id=f"dec-{payload.unit_id}",
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
            unit_id=payload.unit_id,
            arm_id="subject-a",
            propensity=0.5,
            policy_family=PolicyFamily.FIXED_SPLIT,
            policy_version="snapshot-email-1",
            diagnostics=DecisionDiagnostics(reason="fixed_split"),
            candidate_arms=payload.candidate_arms or [],
            context=payload.context,
        )

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate:
        self.exposures.append(payload)
        return payload

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate:
        self.outcomes.append(payload)
        return payload


class _FakeProvider:
    provider_name = "simulator"

    def __init__(self, *, failed_recipient: str | None = None) -> None:
        self.failed_recipient = failed_recipient
        self.plans: list[EmailSendPlan] = []

    def deliver(self, plan: EmailSendPlan) -> DeliveryResult:
        self.plans.append(plan)
        records: list[DeliveryRecord] = []
        for instruction in plan.instructions:
            if instruction.recipient_id == self.failed_recipient:
                records.append(
                    DeliveryRecord(
                        recipient_id=instruction.recipient_id,
                        delivered=False,
                        error="smtp 550",
                    )
                )
                continue
            records.append(
                DeliveryRecord(
                    recipient_id=instruction.recipient_id,
                    delivered=True,
                    provider_message_id=f"msg-{instruction.recipient_id}",
                )
            )

        return DeliveryResult(
            provider=self.provider_name,
            delivered_at=datetime(2026, 3, 14, 20, 30, tzinfo=UTC),
            records=records,
        )


def test_build_send_plan_assigns_each_recipient_in_tranche() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")

    plan = adapter.build_send_plan(
        tranche_id="tranche-1",
        recipients=[
            EmailRecipient(
                recipient_id="u-001",
                address="u-001@example.com",
                context={"tier": "free"},
            ),
            EmailRecipient(
                recipient_id="u-002",
                address="u-002@example.com",
                context={"tier": "pro"},
            ),
        ],
        idempotency_prefix="campaign-2026-03",
        candidate_arms=["subject-a", "subject-b"],
        campaign_context={"campaign": "spring-launch"},
    )

    assert len(client.assign_payloads) == 2
    assert plan.tranche_id == "tranche-1"
    assert [item.recipient_id for item in plan.instructions] == ["u-001", "u-002"]
    assert client.assign_payloads[0].idempotency_key == "campaign-2026-03:tranche-1:u-001"
    assert client.assign_payloads[1].idempotency_key == "campaign-2026-03:tranche-1:u-002"
    assert client.assign_payloads[0].context == {"campaign": "spring-launch", "tier": "free"}


def test_dispatch_send_plan_logs_exposure_for_delivered_records_only() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")

    plan = adapter.build_send_plan(
        tranche_id="tranche-2",
        recipients=[
            EmailRecipient(recipient_id="u-101"),
            EmailRecipient(recipient_id="u-102"),
        ],
        idempotency_prefix="campaign-2026-03",
    )
    provider = _FakeProvider(failed_recipient="u-102")

    result = adapter.dispatch_send_plan(plan=plan, provider=provider)

    assert result.provider == "simulator"
    assert len(result.records) == 2
    assert len(client.exposures) == 1
    exposure = client.exposures[0]
    assert exposure.unit_id == "u-101"
    assert exposure.exposure_type.value == "executed"
    assert exposure.metadata["surface"] == "email"
    assert exposure.metadata["tranche_id"] == "tranche-2"
    assert exposure.metadata["provider_message_id"] == "msg-u-101"


def test_ingest_webhook_maps_event_types_to_outcomes() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")

    occurred_at = datetime(2026, 3, 14, 20, 45, tzinfo=UTC)
    open_outcome = adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id="evt-open-1",
            webhook_type=EmailWebhookType.OPEN,
            recipient_id="u-501",
            decision_id="dec-u-501",
            occurred_at=occurred_at,
        )
    )
    reply_outcome = adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id="evt-reply-1",
            webhook_type=EmailWebhookType.REPLY,
            recipient_id="u-501",
            decision_id="dec-u-501",
            occurred_at=occurred_at,
        )
    )
    complaint_outcome = adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id="evt-complaint-1",
            webhook_type=EmailWebhookType.COMPLAINT,
            recipient_id="u-502",
            decision_id="dec-u-502",
            occurred_at=occurred_at,
            metadata={"provider": "simulator"},
        )
    )

    assert open_outcome is not None
    assert open_outcome.events[0].outcome_type == "email_open"
    assert open_outcome.events[0].timestamp == occurred_at

    assert reply_outcome is not None
    assert reply_outcome.events[0].outcome_type == "email_reply"

    assert complaint_outcome is not None
    assert complaint_outcome.events[0].outcome_type == "email_complaint"
    assert complaint_outcome.metadata["source"] == "email_webhook"
    assert complaint_outcome.metadata["webhook_event_id"] == "evt-complaint-1"
    assert complaint_outcome.metadata["provider"] == "simulator"


def test_ingest_webhook_uses_delayed_timestamp_and_custom_attribution_window() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(
        client=client,
        workspace_id="ws-email",
        job_id="job-email",
        outcome_attribution_window_hours=336,
    )

    occurred_at = datetime(2026, 3, 10, 8, 15, tzinfo=UTC)
    outcome = adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id="evt-conv-1",
            webhook_type=EmailWebhookType.CONVERSION,
            recipient_id="u-601",
            decision_id="dec-u-601",
            occurred_at=occurred_at,
            value=2.0,
        )
    )

    assert outcome is not None
    assert outcome.events[0].outcome_type == "email_conversion"
    assert outcome.events[0].value == 2.0
    assert outcome.events[0].timestamp == occurred_at
    assert outcome.attribution_window.hours == 336


def test_ingest_webhook_is_idempotent_by_webhook_event_id() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")

    event = EmailWebhookEvent(
        webhook_event_id="evt-click-1",
        webhook_type=EmailWebhookType.CLICK,
        recipient_id="u-701",
        decision_id="dec-u-701",
        occurred_at=datetime(2026, 3, 14, 21, 0, tzinfo=UTC),
    )

    first = adapter.ingest_webhook(event=event)
    second = adapter.ingest_webhook(event=event)

    assert first is not None
    assert second is None
    assert len(client.outcomes) == 1
    assert client.outcomes[0].events[0].outcome_type == "email_click"


def test_tranche_planner_refreshes_candidate_arms_between_tranches() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")

    active_arms_versions = [["subject-a", "subject-b"], ["subject-b"]]

    def _active_arms() -> list[str]:
        return active_arms_versions.pop(0)

    planner = EmailTranchePlanner(
        adapter=adapter,
        active_arm_supplier=_active_arms,
        can_send_supplier=lambda: True,
    )

    planner.plan_next_tranche(
        tranche_id="t1",
        recipients=[EmailRecipient(recipient_id="u-801")],
        idempotency_prefix="campaign-2026-03",
    )
    planner.plan_next_tranche(
        tranche_id="t2",
        recipients=[EmailRecipient(recipient_id="u-802")],
        idempotency_prefix="campaign-2026-03",
    )

    assert client.assign_payloads[0].candidate_arms == ["subject-a", "subject-b"]
    assert client.assign_payloads[1].candidate_arms == ["subject-b"]


def test_tranche_planner_blocks_when_job_is_paused() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")
    planner = EmailTranchePlanner(
        adapter=adapter,
        active_arm_supplier=lambda: ["subject-a"],
        can_send_supplier=lambda: False,
    )

    try:
        planner.plan_next_tranche(
            tranche_id="t-paused",
            recipients=[EmailRecipient(recipient_id="u-901")],
            idempotency_prefix="campaign-2026-03",
        )
        raise AssertionError("expected TranchePlanningBlockedError")
    except TranchePlanningBlockedError as exc:
        assert "not sendable" in str(exc)


def test_tranche_planner_blocks_when_no_active_arms() -> None:
    client = _FakeEmailClient()
    adapter = EmailAdapter(client=client, workspace_id="ws-email", job_id="job-email")
    planner = EmailTranchePlanner(
        adapter=adapter,
        active_arm_supplier=lambda: [],
        can_send_supplier=lambda: True,
    )

    try:
        planner.plan_next_tranche(
            tranche_id="t-empty",
            recipients=[EmailRecipient(recipient_id="u-902")],
            idempotency_prefix="campaign-2026-03",
        )
        raise AssertionError("expected TranchePlanningBlockedError")
    except TranchePlanningBlockedError as exc:
        assert "No active arms" in str(exc)
