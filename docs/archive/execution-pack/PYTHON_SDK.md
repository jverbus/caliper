# P5-002 Python SDK

The Python SDK exposes two clients:

- `ServiceCaliperClient`: HTTP client for service mode API usage.
- `EmbeddedCaliperClient`: in-process client for embedded workflows backed by local SQLite/Postgres storage.

## Core operations

Both clients support the main workflow operations:

- create/get/update job
- bulk arm registration
- assignment
- exposure logging
- outcome logging
- report generation

The embedded client also includes pause/resume helpers for local operator flows.

## Example

```python
from caliper_core.models import AssignRequest, ReportGenerateRequest
from caliper_sdk import EmbeddedCaliperClient

client = EmbeddedCaliperClient(db_url="sqlite:///./data/caliper-demo.db")
result = client.assign(
    AssignRequest(
        workspace_id="ws-demo",
        job_id="job_123",
        unit_id="user-1",
        idempotency_key="req-1",
    )
)
report = client.generate_report(
    job_id="job_123",
    payload=ReportGenerateRequest(workspace_id="ws-demo"),
)
```
