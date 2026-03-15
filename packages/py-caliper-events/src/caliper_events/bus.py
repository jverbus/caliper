from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from caliper_core.events import EventEnvelope
from caliper_core.interfaces import EventBus, EventLedger

ProjectionHook = Callable[[EventEnvelope], None]


class KafkaProducer(Protocol):
    """Minimal producer contract shared by kafka-python/confluent wrappers."""

    def send(self, topic: str, *, key: bytes | None = None, value: bytes) -> object: ...


class InlineEventBus(EventBus):
    """In-process pub/sub event bus with optional projection hooks."""

    def __init__(self, hooks: list[ProjectionHook] | None = None) -> None:
        self._hooks: list[ProjectionHook] = hooks or []

    def register_hook(self, hook: ProjectionHook) -> None:
        self._hooks.append(hook)

    def publish(self, event: EventEnvelope) -> None:
        for hook in self._hooks:
            hook(event)


class LedgerBackedEventBus(EventBus):
    """Event bus that persists first, then dispatches to hooks."""

    def __init__(self, ledger: EventLedger, hooks: list[ProjectionHook] | None = None) -> None:
        self._ledger = ledger
        self._inline = InlineEventBus(hooks=hooks)

    def register_hook(self, hook: ProjectionHook) -> None:
        self._inline.register_hook(hook)

    def publish(self, event: EventEnvelope) -> None:
        persisted = self._ledger.append(event)
        self._inline.publish(persisted)


class KafkaEventBus(EventBus):
    """Event bus implementation that publishes envelopes to Kafka topics."""

    def __init__(
        self,
        *,
        producer: KafkaProducer,
        topic_prefix: str = "caliper.events",
        hooks: list[ProjectionHook] | None = None,
    ) -> None:
        self._producer = producer
        self._topic_prefix = topic_prefix
        self._inline = InlineEventBus(hooks=hooks)

    def register_hook(self, hook: ProjectionHook) -> None:
        self._inline.register_hook(hook)

    def publish(self, event: EventEnvelope) -> None:
        topic = self._topic_for(event)
        key = f"{event.workspace_id}:{event.job_id}".encode()
        payload = event.model_dump_json().encode("utf-8")
        self._producer.send(topic, key=key, value=payload)
        self._inline.publish(event)

    def _topic_for(self, event: EventEnvelope) -> str:
        event_suffix = event.event_type.replace(".", "_")
        return f"{self._topic_prefix}.{event_suffix}"
