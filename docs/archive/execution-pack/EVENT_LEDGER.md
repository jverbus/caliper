# Event Ledger and Event Bus

Chunk: **P1-004 Event ledger and event bus**

## What this adds

- `EventEnvelope` persistence through `EventLedger` methods on SQL repositories.
- Append-only event storage in `event_ledger` table.
- Safe idempotent append behavior when `idempotency_key` is provided.
- Replay support by `(workspace_id, job_id)` with optional time window filtering.
- Event bus abstractions in `py-caliper-events`:
  - `InlineEventBus` for in-process hook dispatch.
  - `LedgerBackedEventBus` for persist-then-dispatch behavior.

## API surface

- `SQLRepository.append(event: EventEnvelope) -> EventEnvelope`
- `SQLRepository.replay(workspace_id, job_id, start=None, end=None) -> list[EventEnvelope]`
- `InlineEventBus.register_hook(hook)`
- `InlineEventBus.publish(event)`
- `LedgerBackedEventBus.publish(event)`

## Duplicate handling

When `idempotency_key` is set, `append()` checks for an existing event in the same
`workspace_id + job_id + event_type + idempotency_key` scope and returns the existing envelope
instead of creating a duplicate row.

## Projection hooks

Projection hooks are simple callables:

```python
from caliper_core.events import EventEnvelope

def projection(event: EventEnvelope) -> None:
    ...
```

Register hooks on `InlineEventBus` or pass them to `LedgerBackedEventBus`.
