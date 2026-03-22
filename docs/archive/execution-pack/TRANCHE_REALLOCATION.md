# Tranche reallocation

## Goal

Support tranche-by-tranche email campaign planning that can adapt to policy updates and guardrail actions between sends.

## Components

- `EmailTranchePlanner` coordinates tranche planning on top of `EmailAdapter`.
- `active_arm_supplier` hook refreshes active candidate arms before each tranche.
- `can_send_supplier` hook blocks tranche planning when a job is paused (for example by guardrail auto-actions).
- `TranchePlanningBlockedError` provides a deterministic failure mode when planning cannot proceed.

## Usage pattern

1. Ingest webhook outcomes from prior tranche(s) with `EmailAdapter.ingest_webhook(...)`.
2. Run policy update / guardrail evaluation loop (worker).
3. For the next tranche, call `EmailTranchePlanner.plan_next_tranche(...)`:
   - fetch current active arms,
   - verify job is still sendable,
   - generate a new send plan with refreshed candidate arms.

This keeps reallocation logic outside the adapter core policy engine while ensuring later tranches consume updated policy state.

## Acceptance mapping

- **Tranche planner update loop:** `EmailTranchePlanner.plan_next_tranche(...)` refreshes active arms for every tranche.
- **Policy update between tranches:** candidate arms are supplied per-tranche after updates complete.
- **Traffic caps on offending arms:** capped/held arms are excluded by `active_arm_supplier` and no longer offered as assignment candidates.
- **Guardrail breach can cap or pause:** paused jobs are blocked by `can_send_supplier` and raise `TranchePlanningBlockedError`.
