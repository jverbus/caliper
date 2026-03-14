# Shadow mode scaffold (P9-002)

This chunk adds a non-live shadow evaluation flow so candidate policies can be compared against the active routing policy without affecting production assignment persistence.

## API

### `POST /v1/assign:shadow`

Request shape extends `POST /v1/assign` with:

- `shadow_snapshot_id`: policy snapshot id to evaluate in parallel.

Response:

- `live_decision`: assignment result computed using the active routing policy.
- `shadow_decision`: assignment result computed using the requested shadow snapshot.

## Behavior

- Live routing state remains unchanged.
- Shadow evaluations do **not** create `decision.assigned` rows/events.
- A job audit record is written with action `decision.shadow_evaluated` containing:
  - `shadow_snapshot_id`
  - `live_arm_id`
  - `shadow_arm_id`
  - request idempotency key

## Acceptance mapping

- **Shadow policy state/hook:** shadow snapshot id can be evaluated against the same request context as live.
- **No live-routing impact:** only explicit `/v1/assign` persists decisions/events; `/v1/assign:shadow` is read/evaluate/audit only.
