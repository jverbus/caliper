# API App Skeleton (P2-001)

This chunk introduces the first service-mode FastAPI skeleton with dependency wiring, health checks, and shared-mode auth scaffolding.

## Endpoints

- `GET /health` and `GET /healthz`
  - Lightweight liveness checks.
- `GET /readyz`
  - Readiness check that verifies database connectivity (`SELECT 1`) using the configured profile backend.
- `GET /v1/system/info`
  - Protected placeholder v1 endpoint used to validate auth + dependency wiring.

## Dependency wiring

`apps/api/dependencies.py` provides reusable dependencies for:

- profile-aware settings (`load_settings`)
- DB engine initialization + migration bootstrap
- SQLAlchemy session factory
- storage repository construction (`SQLRepository`)

These are cached process-wide so initialization is deterministic and low-overhead.

## Shared-mode auth scaffold

When `CALIPER_PROFILE=shared`, the API enforces a bearer token on protected endpoints.

- token source: `CALIPER_SHARED_API_TOKEN`
- missing token or invalid token: `401 Unauthorized`
- shared mode without configured token: `503 Service Unavailable`

Health and readiness routes remain unauthenticated to support infrastructure probing.

## Tests

`tests/integration/test_api_app_skeleton.py` covers:

- health/readiness endpoint behavior
- shared-mode bearer-token enforcement on protected routes
