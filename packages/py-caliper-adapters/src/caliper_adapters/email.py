from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from caliper_core.models import (
    AssignRequest,
    AssignResult,
    AttributionWindow,
    ExposureCreate,
    ExposureType,
    OutcomeCreate,
    OutcomeEvent,
)


class EmailAdapterClient(Protocol):
    def assign(self, payload: AssignRequest) -> AssignResult: ...

    def log_exposure(self, payload: ExposureCreate) -> ExposureCreate: ...

    def log_outcome(self, payload: OutcomeCreate) -> OutcomeCreate: ...


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


class EmailWebhookType(StrEnum):
    OPEN = "open"
    CLICK = "click"
    CONVERSION = "conversion"
    REPLY = "reply"
    UNSUBSCRIBE = "unsubscribe"
    COMPLAINT = "complaint"


@dataclass(frozen=True)
class EmailWebhookEvent:
    webhook_event_id: str
    webhook_type: EmailWebhookType
    recipient_id: str
    decision_id: str
    occurred_at: datetime
    value: float = 1.0
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)


class TranchePlanningBlockedError(RuntimeError):
    """Raised when tranche planning is blocked (for example, paused by guardrails)."""


class EmailTranchePlanner:
    """Coordinates tranche-by-tranche planning with policy/guardrail-aware refresh hooks."""

    def __init__(
        self,
        *,
        adapter: EmailAdapter,
        active_arm_supplier: Callable[[], list[str]],
        can_send_supplier: Callable[[], bool],
    ) -> None:
        self._adapter = adapter
        self._active_arm_supplier = active_arm_supplier
        self._can_send_supplier = can_send_supplier

    def plan_next_tranche(
        self,
        *,
        tranche_id: str,
        recipients: list[EmailRecipient],
        idempotency_prefix: str,
        campaign_context: dict[str, str | int | float | bool] | None = None,
    ) -> EmailSendPlan:
        if not self._can_send_supplier():
            msg = "Job is not sendable (likely paused by guardrail action)"
            raise TranchePlanningBlockedError(msg)

        candidate_arms = self._active_arm_supplier()
        if len(candidate_arms) == 0:
            msg = "No active arms available for tranche planning"
            raise TranchePlanningBlockedError(msg)

        return self._adapter.build_send_plan(
            tranche_id=tranche_id,
            recipients=recipients,
            idempotency_prefix=idempotency_prefix,
            candidate_arms=candidate_arms,
            campaign_context=campaign_context,
        )


class EmailAdapter:
    """Email-facing adapter for tranche assignment and provider handoff."""

    def __init__(
        self,
        *,
        client: EmailAdapterClient,
        workspace_id: str,
        job_id: str,
        open_metric: str = "email_open",
        click_metric: str = "email_click",
        conversion_metric: str = "email_conversion",
        reply_metric: str = "email_reply",
        unsubscribe_metric: str = "email_unsubscribe",
        complaint_metric: str = "email_complaint",
        outcome_attribution_window_hours: int = 168,
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._job_id = job_id
        self._open_metric = open_metric
        self._click_metric = click_metric
        self._conversion_metric = conversion_metric
        self._reply_metric = reply_metric
        self._unsubscribe_metric = unsubscribe_metric
        self._complaint_metric = complaint_metric
        self._outcome_attribution_window_hours = outcome_attribution_window_hours
        self._processed_webhook_ids: set[str] = set()

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
                    idempotency_key=(f"{idempotency_prefix}:{tranche_id}:{recipient.recipient_id}"),
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

    def ingest_webhook(self, *, event: EmailWebhookEvent) -> OutcomeCreate | None:
        """Map webhook events to Caliper outcomes with duplicate-safe handling."""
        if event.webhook_event_id in self._processed_webhook_ids:
            return None

        metric = self._metric_for_webhook(event.webhook_type)
        outcome = self._client.log_outcome(
            OutcomeCreate(
                workspace_id=self._workspace_id,
                job_id=self._job_id,
                decision_id=event.decision_id,
                unit_id=event.recipient_id,
                events=[
                    OutcomeEvent(
                        outcome_type=metric,
                        value=event.value,
                        timestamp=event.occurred_at,
                    )
                ],
                attribution_window=AttributionWindow(hours=self._outcome_attribution_window_hours),
                metadata={
                    "source": "email_webhook",
                    "surface": "email",
                    "webhook_event_id": event.webhook_event_id,
                    "webhook_type": event.webhook_type.value,
                    **dict(event.metadata),
                },
            )
        )
        self._processed_webhook_ids.add(event.webhook_event_id)
        return outcome

    def _metric_for_webhook(self, webhook_type: EmailWebhookType) -> str:
        metric_map = {
            EmailWebhookType.OPEN: self._open_metric,
            EmailWebhookType.CLICK: self._click_metric,
            EmailWebhookType.CONVERSION: self._conversion_metric,
            EmailWebhookType.REPLY: self._reply_metric,
            EmailWebhookType.UNSUBSCRIBE: self._unsubscribe_metric,
            EmailWebhookType.COMPLAINT: self._complaint_metric,
        }
        return metric_map[webhook_type]
