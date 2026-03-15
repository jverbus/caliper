# C4 Report Summary Correctness (Arm-Scoped Exposures/Outcomes)

## Goal
Ensure report `leaders` summary rows are correctness-safe by scoping `exposures` and `outcomes` to each arm, instead of repeating global totals per arm.

## Changes
- Updated `ReportGenerator.generate()` to accept full exposure records (`list[ExposureCreate]`) rather than only a global exposure count.
- Added decision-to-arm indexing and per-arm counters:
  - `exposures_by_arm`: counts exposure records whose `decision_id` maps to each arm.
  - `outcomes_by_arm`: counts outcome records whose `decision_id` maps to each arm.
- Updated `ReportSummary` population so each row reports arm-scoped values:
  - `exposures = exposures_by_arm[arm_id]`
  - `outcomes = outcomes_by_arm[arm_id]`
- Kept top-level report totals stable:
  - `Total exposures = len(exposures)`
  - `Total outcome events = sum(len(events) for each outcome)`

## Parity Updates
Updated all call sites to pass full exposure records:
- API report generation path (`apps/api/main.py`)
- Worker report task path (`apps/worker/loop.py`)
- Embedded Python SDK report path (`packages/py-sdk/src/caliper_sdk/client.py`)

## Tests
- Updated existing report rendering unit test to pass exposure records.
- Added `test_report_summary_uses_arm_scoped_exposure_and_outcome_counts` to verify:
  - multiple exposures map correctly by arm
  - outcomes are counted only on the owning arm

## Validation
Ran:
- `make lint`
- `make typecheck`
- `make test`

All checks passed.
