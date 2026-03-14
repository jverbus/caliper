"""Caliper adapter helpers for surface-specific integrations."""

from caliper_adapters.email import (
    DeliveryRecord,
    DeliveryResult,
    EmailAdapter,
    EmailRecipient,
    EmailSendInstruction,
    EmailSendPlan,
    EmailWebhookEvent,
    EmailWebhookType,
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
    "EmailWebhookEvent",
    "EmailWebhookType",
    "WebAdapter",
    "WebAssignment",
    "WorkflowAdapter",
    "WorkflowAssignment",
]
