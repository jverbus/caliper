from __future__ import annotations

from collections.abc import Callable

from caliper_core.events import EventEnvelope
from caliper_core.interfaces import EventBus, EventLedger

ProjectionHook = Callable[[EventEnvelope], None]


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
