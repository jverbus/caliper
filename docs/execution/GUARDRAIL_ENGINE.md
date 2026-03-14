# P4-005 Guardrail engine and auto actions

## Scope

Implements guardrail evaluation in the worker policy-update path with automatic mitigation actions:

- evaluates `guardrail_spec.rules` against policy-update reward records
- emits persistent guardrail breach events for reporting/audit
- applies configured actions: annotate, cap, demote, pause, require manual resume

## Evaluation behavior

- Guardrails are evaluated during `run_policy_update` tasks.
- Metric values are computed from reward dataset records using average observed metric value.
- A breach is recorded when a rule comparison (`>`, `>=`, `<`, `<=`, `==`, `!=`) returns true.
- Breach metadata stores operator, threshold, observed value, and selected target arm (if any).

## Auto-action behavior

- `annotate`: record event only
- `cap` / `demote`: place highest-risk arm in `held_out` state
- `pause`: transition job to `paused`
- `require_manual_resume`: transition job to `paused` with `approval_state=pending`

All executed actions append `worker.guardrail.action` audit records.

## Reporting surface

Guardrail events are persisted in `guardrail_events` and included in report generation via existing report guardrail sections.

## Tests

- `tests/unit/test_guardrail_engine.py` validates breach detection and target-arm selection.
- `tests/integration/test_worker_scheduler.py::test_worker_guardrail_breach_pauses_job_and_records_event` validates worker-driven guardrail action + persistence.
