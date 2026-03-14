# Context schema versioning

Chunk: **P9-001 Context schema versioning**

## What this adds

- Assignment requests can now enforce a versioned context contract via `policy_spec.context_schema_version`.
- Validation and redaction hooks run before assignment decisions are computed or persisted.
- Stored decision context follows a strict storage policy: only schema-allowed fields are retained, and configured sensitive fields are redacted.

## Policy contract

When `policy_spec.context_schema_version` is set, define matching schema rules under:

- `policy_spec.params.context_schemas`
- keyed by version (for example `"v1"`)

Schema config supports:

- `required_fields`: context keys that must exist
- `allowed_fields`: optional allow-list; any extra keys are rejected
- `redact_fields`: keys to mask in persisted context

Example:

```json
{
  "policy_spec": {
    "policy_family": "fixed_split",
    "context_schema_version": "v1",
    "params": {
      "weights": {"arm-a": 0.5, "arm-b": 0.5},
      "context_schemas": {
        "v1": {
          "required_fields": ["country"],
          "allowed_fields": ["country", "device_type", "email"],
          "redact_fields": ["email"]
        }
      }
    }
  }
}
```

## Validation behavior

`POST /v1/assign` returns `400` when:

- a required context field is missing,
- disallowed fields are supplied (when `allowed_fields` is configured),
- a schema version is configured but no matching schema config exists.

## Storage policy

- Decision records persist the schema version in `context_schema_version`.
- Decision context and `decision.assigned` event payload store **sanitized** context only.
- Redacted fields are replaced with the literal marker `"[REDACTED]"`.

## Acceptance mapping

- Decision envelope supports versioned context: covered by assign response + decision persistence tests.
- Missing/disallowed field validation: covered by integration tests in `tests/integration/test_api_assign.py`.
