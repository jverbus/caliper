from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from caliper_core.models import AssignRequest, AssignResult, ExposureCreate, ExposureType


class EmailAdapterClient(Protocol):
    def assign(self, payload: AssignRequest) -> AssignResult: ...

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate: ...


@dataclass(frozen=True)
class EmailRecipient:
    recipient_id: str
    address: str | None = None
    context: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailSendInstruction:
    recipient_id: str
    decision_id: str
    arm_id: str
    propensity: float
    policy_version: str
    policy_family: str
    address: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailSendPlan:
    workspace_id: str
    job_id: str
    tranche_id: str
    generated_at: datetime
    instructions: list[EmailSendInstruction]


@dataclass(frozen=True)
class DeliveryRecord:
    recipient_id: str
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    delivered_at: datetime
    records: list[DeliveryRecord]


class EmailDeliveryProvider(Protocol):
    provider_name: str

    def deliver(self, plan: EmailSendPlan) -> DeliveryResult: ...


class EmailAdapter:
    """Email-facing adapter for tranche assignment and provider handoff."""

    def __init__(
        self,
        *,
        client: EmailAdapterClient,
        workspace_id: str,
        job_id: str,
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._job_id = job_id

    def build_send_plan(
        self,
        *,
        tranche_id: str,
        recipients: list[EmailRecipient],
        idempotency_prefix: str,
        candidate_arms: list[str] | None = None,
        campaign_context: dict[str, str | int | float | bool] | None = None,
    ) -> EmailSendPlan:
        instructions: list[EmailSendInstruction] = []
        base_context = dict(campaign_context or {})
        for recipient in recipients:
            assignment = self._client.assign(
                AssignRequest(
                    workspace_id=self._workspace_id,
                    job_id=self._job_id,
                    unit_id=recipient.recipient_id,
                    candidate_arms=candidate_arms,
                    context={**base_context, **recipient.context},
                    idempotency_key=(
                        f"{idempotency_prefix}:{tranche_id}:{recipient.recipient_id}"
                    ),
                )
            )
            instructions.append(
                EmailSendInstruction(
                    recipient_id=recipient.recipient_id,
                    decision_id=assignment.decision_id,
                    arm_id=assignment.arm_id,
                    propensity=assignment.propensity,
                    policy_version=assignment.policy_version,
                    policy_family=assignment.policy_family.value,
                    address=recipient.address,
                    metadata={
                        "surface": "email",
                        "tranche_id": tranche_id,
                    },
                )
            )

        return EmailSendPlan(
            workspace_id=self._workspace_id,
            job_id=self._job_id,
            tranche_id=tranche_id,
            generated_at=datetime.now(tz=UTC),
            instructions=instructions,
        )

    def dispatch_send_plan(
        self,
        *,
        plan: EmailSendPlan,
        provider: EmailDeliveryProvider,
    ) -> DeliveryResult:
        delivery = provider.deliver(plan)
        instruction_by_recipient = {item.recipient_id: item for item in plan.instructions}
        for record in delivery.records:
            if not record.delivered:
                continue
            instruction = instruction_by_recipient.get(record.recipient_id)
            if instruction is None:
                continue
            self._client.log_exposure(
                ExposureCreate(
                    workspace_id=self._workspace_id,
                    job_id=self._job_id,
                    decision_id=instruction.decision_id,
                    unit_id=record.recipient_id,
                    exposure_type=ExposureType.EXECUTED,
                    metadata={
                        "surface": "email",
                        "tranche_id": plan.tranche_id,
                        "provider": delivery.provider,
                        "provider_message_id": record.provider_message_id,
                    },
                )
            )

        return delivery
