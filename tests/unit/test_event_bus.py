from __future__ import annotations

import json

from caliper_core.events import EventEnvelope
from caliper_events import InlineEventBus, KafkaEventBus, LedgerBackedEventBus
from caliper_storage.engine import build_engine, init_db, make_session_factory
from caliper_storage.repositories import SQLiteRepository


def test_inline_event_bus_dispatches_registered_hooks() -> None:
    seen: list[str] = []
    bus = InlineEventBus()
    bus.register_hook(lambda event: seen.append(event.event_id))

    bus.publish(
        EventEnvelope(
            event_id="evt_inline",
            workspace_id="ws-1",
            job_id="job-1",
            event_type="job.created",
        )
    )

    assert seen == ["evt_inline"]


def test_ledger_backed_event_bus_persists_before_dispatch() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    ledger = SQLiteRepository(make_session_factory(engine))

    seen: list[str] = []
    bus = LedgerBackedEventBus(ledger=ledger, hooks=[lambda event: seen.append(event.event_id)])

    bus.publish(
        EventEnvelope(
            event_id="evt_persist",
            workspace_id="ws-1",
            job_id="job-1",
            event_type="job.updated",
            payload={"name": "new"},
        )
    )

    replayed = ledger.replay(workspace_id="ws-1", job_id="job-1")
    assert [event.event_id for event in replayed] == ["evt_persist"]
    assert seen == ["evt_persist"]


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes | None, bytes]] = []

    def send(self, topic: str, *, key: bytes | None = None, value: bytes) -> object:
        self.messages.append((topic, key, value))
        return object()


def test_kafka_event_bus_publishes_with_topic_partition_key_and_payload() -> None:
    producer = FakeKafkaProducer()
    seen: list[str] = []
    bus = KafkaEventBus(producer=producer, hooks=[lambda event: seen.append(event.event_id)])

    bus.publish(
        EventEnvelope(
            event_id="evt_kafka",
            workspace_id="ws-1",
            job_id="job-1",
            event_type="decision.assigned",
            payload={"arm_id": "arm-a", "propensity": 0.7},
        )
    )

    assert len(producer.messages) == 1
    topic, key, value = producer.messages[0]
    assert topic == "caliper.events.decision_assigned"
    assert key == b"ws-1:job-1"

    encoded = json.loads(value.decode("utf-8"))
    assert encoded["event_id"] == "evt_kafka"
    assert encoded["event_type"] == "decision.assigned"
    assert encoded["payload"]["arm_id"] == "arm-a"
    assert seen == ["evt_kafka"]
