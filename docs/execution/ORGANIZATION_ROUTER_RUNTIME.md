# Organization router runtime (PV1-004)

This chunk adds a first-pass org-router runtime adapter for post-v1 routing experiments.

## What this introduces

- `OrgRouterAdapter` in `py-caliper-adapters` for organization-level task routing.
- `route_task(...)` helper that:
  - calls `assign` with `surface=org_router` context,
  - logs an `executed` exposure for the routed organization arm,
  - returns a compact `OrganizationRoute` payload with optional `child_policy_ref`.
- `log_task_completion(...)` helper that records:
  - objective value,
  - latency metric,
  - cost metric,
  - optional downstream outcome events (e.g. handoff success).

## Runtime contract

`OrgRouterAdapter` expects a client implementing:

- `assign(AssignRequest) -> AssignResult`
- `log_exposure(ExposureCreate) -> ExposureCreate`
- `log_outcome(OutcomeCreate) -> OutcomeCreate`

This mirrors existing `WorkflowAdapter` and `WebAdapter` usage patterns so callers can wire the same service or embedded clients.

## Child-policy linkage

To keep runtime scope simple, child-policy routing is represented by an optional static mapping:

- `child_policy_refs: dict[str, str]`

Where key = organization arm id and value = child policy reference string. The adapter returns the mapped value in `OrganizationRoute.child_policy_ref` when present.

## Acceptance mapping

- Organization route assignment uses Caliper's standard assignment contract with candidate-arm subsets.
- Routed assignments log executed exposures for auditability.
- Router outcomes include quality/speed/cost metrics and can attach downstream events for richer org-level measurement.
