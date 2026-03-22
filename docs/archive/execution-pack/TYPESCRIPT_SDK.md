# P6-001 TypeScript SDK

The TypeScript SDK provides a service-mode client for core Caliper operations against the live API.

## Package

- Location: `packages/ts-sdk`
- Import: `@caliper/ts-sdk`
- Client: `CaliperClient`

## Supported operations

- `healthz()`
- `createJob(payload)`
- `getJob(jobId)`
- `updateJob(jobId, patch)`
- `addArms(jobId, payload)`
- `assign(payload)`
- `logExposure(payload)`
- `logOutcome(payload)`
- `generateReport(jobId, payload)`
- `latestReport(jobId, workspaceId)`

## Example

```ts
import { CaliperClient } from "@caliper/ts-sdk";

const client = new CaliperClient({ baseUrl: "http://127.0.0.1:8000" });
const health = await client.healthz();
```

## Acceptance mapping

- TS SDK compiles via `pnpm --filter @caliper/ts-sdk build`.
- Integration coverage (`tests/integration/test_ts_sdk_service.py`) runs a live API process and verifies TS SDK calls for job/arm/assign/exposure/outcome/report flows.
