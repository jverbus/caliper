# C5 Replay/OBP/Shadow-Diff Promotion Gate Hardening

## Goal

Harden contextual promotion gating by requiring explicit non-live validation evidence tied to the candidate snapshot before activation.

## What changed

- Added `POST /v1/jobs/{job_id}/policy-snapshots/{snapshot_id}:run-promotion-checks`.
- Promotion checks now compute and persist a snapshot-scoped audit record (`policy.snapshot.promotion_checks.completed`) containing:
  - replay readiness (`replay_ready`, record count, average reward)
  - shadow-vs-live diff readiness (`shadow_diff_ready`, compared count, disagreement rate)
  - OBP payload readiness (`obp_ready`, optional error details)
- Contextual gate enforcement now requires a successful promotion-check audit for the same snapshot instead of only checking for generic shadow evaluation activity.

## Behavior details

- Replay check uses replay-export/OPE scaffolding when `caliper_ope` is importable in the runtime.
- If `caliper_ope` is unavailable, checks are recorded as not-ready with an explicit runtime error message.
- Shadow-vs-live diff compares persisted live decisions against non-live reassignment under the candidate snapshot policy.
- Gate failure reasons are now explicit for each missing validation area (replay, shadow diff, OBP).

## Acceptance mapping

- ✅ Promotion gate blocks contextual activation when checks have not been executed for that snapshot.
- ✅ Promotion gate allows contextual activation after promotion checks complete with replay+shadow+OBP readiness.
- ✅ New check run is auditable and snapshot-scoped for later operator review.
