# Exposure Ingest (P3-003)

This chunk adds `POST /v1/exposures` for logging rendered/executed assignment exposures, persisting canonical exposure events, and enforcing duplicate-safe ingest.

## Endpoint

- **Path:** `/v1/exposures`
- **Request model:** `ExposureCreate`
- **Response model:** `ExposureCreate`

Behavior:

1. Validate job existence and workspace scope.
2. Validate referenced decision exists.
3. Validate decision context matches the request (`workspace_id`, `job_id`, `unit_id`).
4. Persist an exposure row to exposure storage.
5. Persist canonical `decision.exposed` event envelope.
6. Record idempotent response keyed by deterministic request hash.
7. Append an audit entry.

## Duplicate-safe handling

- The endpoint uses deterministic request-hash idempotency for exposure writes.
- A byte-identical retry returns the original response and does not write duplicate exposure/event rows.
- This keeps retries safe even without caller-supplied idempotency headers in v1.

## Acceptance mapping

- **Exposure stored separately from decision:** exposure rows are persisted to `exposures` and validated independently from decision rows.
- **Duplicate handling is safe:** identical retries return stable responses and produce one persisted exposure + one `decision.exposed` event.
