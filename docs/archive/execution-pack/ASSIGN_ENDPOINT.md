# Assign Endpoint and Idempotency (P3-002)

This chunk adds `POST /v1/assign` with deterministic fixed-split assignment, database-backed idempotency, and assignment event persistence.

## Endpoint

- **Path:** `/v1/assign`
- **Request model:** `AssignRequest`
- **Response model:** `AssignResult`

Behavior:

1. Validate job existence and workspace scope.
2. Check idempotency store (`workspace_id + endpoint + idempotency_key`).
3. If found with matching request hash, return cached decision.
4. If found with a different request hash, return `409`.
5. Otherwise compute a decision through `AssignmentEngine` using active arms and optional `candidate_arms` filter.
6. Persist decision row.
7. Persist canonical `decision.assigned` event envelope.
8. Persist idempotency record with request hash + serialized response.
9. Append an audit entry.

## Idempotency persistence

- New table: `idempotency_keys`
- Unique scope index: `(workspace_id, endpoint, idempotency_key)`
- Stored values:
  - request hash (`sha256` over canonical JSON payload)
  - serialized response body
  - creation timestamp

This guarantees stable retries for the same request and blocks key reuse with conflicting payloads.

## Acceptance mapping

- **Retries are stable:** cached `AssignResult` is returned for matching retries.
- **Candidate subsets respected:** assignment engine filters to provided candidate set.
- **`decision.assigned` persisted:** event ledger receives and stores the canonical assignment event.
