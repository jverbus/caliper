# Replay Export and OPE Scaffold

Chunk: **P9-003 Replay export and OPE scaffold**

## What shipped

- Added replay dataset export helpers in `py-caliper-ope`:
  - `ReplayExporter` builds deterministic per-decision replay rows from persisted decisions/exposures/outcomes.
  - `ReplayRecord` includes required OPE fields:
    - `context`
    - `chosen_action`
    - `propensity`
    - `reward`
    - `assigned_at` plus exposure/outcome timestamps
- Added OPE scaffold contracts:
  - `OPEEstimator` protocol for future estimators
  - `DatasetSummary` + `summarize_dataset` utility for baseline dataset inspection

## Replay dataset behavior

For each decision in `(workspace_id, job_id)` ordered by assignment time:

- `chosen_action` is the decision arm id
- `propensity` is copied from assignment
- `context` is copied from assignment payload (already redacted by policy where applicable)
- `reward` is computed as the sum of all persisted outcome event values for that decision
- `assigned_at` is the assignment timestamp
- `first_exposed_at` is the earliest exposure timestamp for that decision (if present)
- `latest_outcome_at` is the latest outcome-event timestamp for that decision (if present)

## Acceptance mapping

- **Exports contain context, chosen action, propensity, reward, and timestamps**
  - Covered by `tests/unit/test_replay_export.py`
- **`py-caliper-ope` scaffold exists for future contextual/OPE work**
  - Implemented by `caliper_ope.replay` + `caliper_ope.estimators`
