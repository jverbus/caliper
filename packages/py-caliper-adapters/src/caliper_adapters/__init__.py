"""Caliper adapter helpers for surface-specific integrations."""

from caliper_adapters.email import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
    EmailSendInstruction,
    EmailSendPlan,
    EmailTranchePlanner,
    EmailWebhookEvent,
    EmailWebhookType,
    TranchePlanningBlockedError,
)
from caliper_adapters.web import WebAdapter, WebAssignment
from caliper_adapters.workflow import WorkflowAdapter, WorkflowAssignment

__all__ = [
    "DeliveryRecord",
    "DeliveryResult",
    "EmailAdapter",
    "EmailRecipient",
    "EmailSendInstruction",
    "EmailSendPlan",
    "EmailTranchePlanner",
    "EmailWebhookEvent",
    "EmailWebhookType",
    "TranchePlanningBlockedError",
    "WebAdapter",
    "WebAssignment",
    "WorkflowAdapter",
    "WorkflowAssignment",
]
