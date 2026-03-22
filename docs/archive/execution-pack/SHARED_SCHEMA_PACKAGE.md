# Shared Schema Package

Phase chunk **P1-001** introduces a shared schema surface in `py-caliper-core`.

## Location

- `packages/py-caliper-core/src/caliper_core/models.py` — canonical domain and API models
- `packages/py-caliper-core/src/caliper_core/schemas.py` — registry and JSON Schema generation

## Programmatic usage

```python
from caliper_core.schemas import DOMAIN_MODELS, generate_json_schemas

schemas = generate_json_schemas()
job_create_schema = schemas["job_create"]
```

## Coverage

The shared schema package currently includes:

- Job create/read/patch and create response
- Arm model
- Assign request/result models
- Exposure and outcome ingest models
- Guardrail event and policy snapshot models
