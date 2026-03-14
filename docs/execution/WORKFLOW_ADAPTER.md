# Workflow Adapter

Chunk: **P5-003 Workflow adapter**

## Scope

Provides a Python adapter API for workflow surfaces that wraps core Caliper operations:

- request-time assignment,
- execution exposure logging,
- latency and cost outcome logging,
- optional human acceptance outcome logging.

## API

Module: `caliper_adapters.workflow`

### `WorkflowAdapter`

Construct with:

- `client`: SDK-like client implementing `assign`, `log_exposure`, `log_outcome`
- `workspace_id`
- `job_id`
- optional metric names: `latency_metric`, `cost_metric`, `acceptance_metric`

### `assign_workflow(...)`

- Calls assignment with optional candidate arm constraints and context.
- Automatically records an `executed` exposure event for workflow execution.
- Returns lightweight `WorkflowAssignment` (`decision_id`, `arm_id`, `propensity`).

### `log_execution_outcome(...)`

Records a single outcome payload with three events:

1. `objective` event (primary reward signal),
2. latency metric event (default `latency_ms`),
3. cost metric event (default `cost_usd`).

This keeps objective + operational metrics co-attributed to one decision.

### `log_human_acceptance(...)`

Optional helper to record a binary acceptance signal (1.0 / 0.0), including reviewer metadata.

Useful for workflows that require manual approval after an automated recommendation.

## Validation Coverage

`tests/unit/test_workflow_adapter.py` verifies:

- assignment wiring and executed exposure behavior,
- latency/cost/objective outcome payload construction,
- optional human acceptance outcome behavior.
