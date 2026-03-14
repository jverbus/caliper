# API and Event Contracts

This document defines the external contracts Caliper must expose in v1.

## 1. Contract principles

1. Embedded mode and service mode must share the same logical operations.
2. Every assignment must return a stable decision ID.
3. Every decision must carry a propensity.
4. Exposure is not the same as assignment.
5. Outcomes may be delayed and arrive asynchronously.
6. All write endpoints must support idempotency.

## 2. Required HTTP endpoints

### 2.1 Jobs

- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `PATCH /v1/jobs/{job_id}`
- `POST /v1/jobs/{job_id}/pause`
- `POST /v1/jobs/{job_id}/resume`
- `POST /v1/jobs/{job_id}/archive`

### 2.2 Arms

- `POST /v1/jobs/{job_id}/arms:batch_register`
- `PATCH /v1/jobs/{job_id}/arms/{arm_id}`
- `POST /v1/jobs/{job_id}/arms/{arm_id}/retire`
- `POST /v1/jobs/{job_id}/arms/{arm_id}/hold_out`
- `POST /v1/jobs/{job_id}/arms/{arm_id}/resume`

### 2.3 Assignment and ingest

- `POST /v1/assign`
- `POST /v1/exposures`
- `POST /v1/outcomes`

### 2.4 Reports

- `POST /v1/jobs/{job_id}/reports:generate`
- `GET /v1/jobs/{job_id}/reports/latest`
- `GET /v1/jobs/{job_id}/metrics`

### 2.5 Audit and health

- `GET /v1/jobs/{job_id}/audit`
- `GET /healthz`
- `GET /readyz`

## 3. Job create contract

Example request:

```json
{
  "workspace_id": "ws_demo",
  "name": "landing-page-signup-test",
  "surface_type": "web",
  "objective_spec": {
    "reward_formula": "1.0 * signup + 0.2 * qualified_demo",
    "penalties": ["0.05 * token_cost_usd", "0.02 * p95_latency_seconds"]
  },
  "guardrail_spec": {
    "rules": [
      {"metric": "error_rate", "op": "<", "threshold": 0.01, "action": "pause"},
      {"metric": "unsubscribe_rate", "op": "<", "threshold": 0.004, "action": "cap"}
    ]
  },
  "policy_spec": {
    "policy_family": "thompson_sampling",
    "params": {"reward_type": "bernoulli"},
    "update_cadence": {"mode": "periodic", "seconds": 300},
    "context_schema_version": null
  },
  "segment_spec": {
    "dimensions": ["country", "device_type"]
  },
  "schedule_spec": {
    "report_cron": "0 7 * * *"
  }
}
```

Example response:

```json
{
  "job_id": "job_123",
  "status": "draft",
  "created_at": "2026-03-14T08:00:00Z"
}
```

## 4. Arm batch registration contract

Example request:

```json
{
  "arms": [
    {
      "arm_id": "arm_a",
      "name": "Variant A",
      "arm_type": "artifact",
      "payload_ref": "file://variants/a.html",
      "metadata": {"headline": "fastest setup"}
    },
    {
      "arm_id": "arm_b",
      "name": "Variant B",
      "arm_type": "artifact",
      "payload_ref": "file://variants/b.html",
      "metadata": {"headline": "highest ROI"}
    }
  ]
}
```

## 5. Assignment contract

Example request:

```json
{
  "workspace_id": "ws_demo",
  "job_id": "job_123",
  "unit_id": "visitor_456",
  "candidate_arms": ["arm_a", "arm_b"],
  "context": {
    "country": "US",
    "device_type": "mobile",
    "segment": "paid_search"
  },
  "idempotency_key": "req_789"
}
```

Example response:

```json
{
  "decision_id": "dec_001",
  "job_id": "job_123",
  "arm_id": "arm_b",
  "propensity": 0.42,
  "policy_family": "thompson_sampling",
  "policy_version": "2026-03-14.1",
  "context_schema_version": null,
  "diagnostics": {
    "scores": {"arm_a": 0.51, "arm_b": 0.57},
    "reason": "highest_sampled_value",
    "fallback_used": false
  }
}
```

### Assignment rules

- `candidate_arms` is optional. If omitted, use all eligible arms.
- If provided, the chosen arm must come from that set.
- If the same idempotency key is retried for the same job and unit, the response must be stable.
- If the current policy cannot score, the engine must use a safe fallback policy and mark that in diagnostics.

## 6. Exposure contract

Exposure must only be logged once the decision was actually rendered or executed.

Example request:

```json
{
  "workspace_id": "ws_demo",
  "job_id": "job_123",
  "decision_id": "dec_001",
  "unit_id": "visitor_456",
  "exposure_type": "rendered",
  "timestamp": "2026-03-14T08:01:00Z",
  "metadata": {
    "page": "/pricing",
    "http_status": 200
  }
}
```

## 7. Outcome contract

Outcomes must support binary, numeric, cost, latency, and named events.

Example request:

```json
{
  "workspace_id": "ws_demo",
  "job_id": "job_123",
  "decision_id": "dec_001",
  "unit_id": "visitor_456",
  "events": [
    {"outcome_type": "click", "value": 1, "timestamp": "2026-03-14T08:01:12Z"},
    {"outcome_type": "signup", "value": 1, "timestamp": "2026-03-14T08:05:40Z"},
    {"outcome_type": "token_cost_usd", "value": 0.03, "timestamp": "2026-03-14T08:05:40Z"},
    {"outcome_type": "p95_latency_seconds", "value": 1.2, "timestamp": "2026-03-14T08:05:40Z"}
  ],
  "attribution_window": {"hours": 24},
  "metadata": {"source": "webhook"}
}
```

## 8. Report contract

Minimum report schema:

```json
{
  "job_id": "job_123",
  "window": {"start": "2026-03-13T07:00:00Z", "end": "2026-03-14T07:00:00Z"},
  "status": "active",
  "policy_family": "thompson_sampling",
  "policy_version": "2026-03-14.3",
  "leaders": [
    {
      "arm_id": "arm_b",
      "rank": 1,
      "estimated_reward": 0.62,
      "traffic_share": 0.48
    }
  ],
  "traffic_shifts": [
    {"arm_id": "arm_b", "from": 0.20, "to": 0.48, "reason": "higher_observed_reward"}
  ],
  "guardrails": [
    {"metric": "unsubscribe_rate", "status": "ok"}
  ],
  "segment_findings": [
    {"segment": {"country": "US"}, "leading_arm_id": "arm_b"}
  ],
  "recommendations": [
    {"action": "continue", "reason": "clear leader but still gathering evidence"}
  ]
}
```

## 9. Canonical event types

Required event names:

- `job.created`
- `job.updated`
- `job.state_changed`
- `arm.registered`
- `arm.updated`
- `arm.state_changed`
- `decision.assigned`
- `decision.exposed`
- `outcome.observed`
- `guardrail.triggered`
- `policy.updated`
- `report.generated`

## 10. Minimum decision envelope

Every `decision.assigned` event must include:

```json
{
  "decision_id": "dec_001",
  "workspace_id": "ws_demo",
  "job_id": "job_123",
  "unit_id": "visitor_456",
  "candidate_arms": ["arm_a", "arm_b"],
  "chosen_arm": "arm_b",
  "propensity": 0.42,
  "policy_family": "thompson_sampling",
  "policy_version": "2026-03-14.1",
  "context_schema_version": null,
  "context": {"country": "US", "device_type": "mobile"},
  "diagnostics": {"reason": "highest_sampled_value"},
  "timestamp": "2026-03-14T08:00:00Z"
}
```

## 11. Idempotency rules

All write endpoints must support idempotency.

Required behavior:

- retries must not create duplicate decisions, exposures, or outcomes,
- duplicate events must either be ignored safely or return the original result,
- idempotency keys must be persisted with enough scope to prevent collisions.

Initial v1 recommendation:

- database-backed idempotency table keyed by workspace, endpoint, and idempotency key.

## 12. Versioning rules

- API path version is `/v1`.
- policy versions are immutable and timestamped or monotonic.
- context schema version may be null for non-contextual jobs.
- report schema version must be explicit if the format changes later.

## 13. Embedded-mode equivalence

The Python SDK and embedded runtime should expose method names that map directly to these logical operations.

Example:

- `create_job()`
- `batch_register_arms()`
- `assign()`
- `log_exposure()`
- `log_outcomes()`
- `generate_report()`

Embedded mode should not invent a different domain contract.
