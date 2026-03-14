from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from caliper_adapters import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
    EmailSendPlan,
)
from caliper_core.models import AssignResult, DecisionDiagnostics, ExposureCreate, PolicyFamily


class _FakeEmailClient:
    def __init__(self) -> None:
        self.assign_payloads: list[Any] = []
        self.exposures: list[ExposureCreate] = []

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
