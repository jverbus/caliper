# PV1-005 Kafka event bus

This chunk adds a Kafka-backed event bus implementation for deployments that need durable, external event fan-out.

## Deliverables

- `KafkaEventBus` in `py-caliper-events` that publishes `EventEnvelope` payloads to Kafka.
- Default topic mapping from canonical event type:
  - `decision.assigned` -> `caliper.events.decision_assigned`
- Partition key strategy for per-job ordering:
  - `"{workspace_id}:{job_id}"`
- Hook compatibility parity with existing event buses so projection/update hooks can still run in-process.
- Unit coverage for topic resolution, key shaping, payload encoding, and hook dispatch.

## Usage

```python
from caliper_events import KafkaEventBus

# producer must expose send(topic, key=..., value=...)
bus = KafkaEventBus(producer=my_kafka_producer)

bus.publish(event_envelope)
```

## Notes

- The Kafka producer interface is intentionally minimal to support wrappers around either `kafka-python` or `confluent-kafka`.
- This chunk provides the runtime event bus implementation seam; environment-specific producer wiring remains deployment-specific.
