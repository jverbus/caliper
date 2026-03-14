# P5-001 CLI

Caliper CLI wraps the core API flows so operators can run major workflows without crafting raw HTTP requests.

## Commands

All commands accept:

- `--api-url` (default `http://127.0.0.1:8000`, or `CALIPER_API_URL`)
- `--api-token` (or `CALIPER_API_TOKEN`) for shared-mode auth

### Job and arm setup

- `create-job`
- `add-arms`

### Decision loop operations

- `assign`
- `log-exposure`
- `log-outcome`
- `generate-report`

### Lifecycle controls

- `pause-job`
- `resume-job`

## Example flow

```bash
uv run python apps/cli/main.py create-job \
  --workspace-id ws-demo \
  --name "Homepage ranking" \
  --objective-spec '{"reward_formula":"signup","penalties":[]}' \
  --guardrail-spec '{"rules":[]}' \
  --policy-spec '{"policy_family":"fixed_split","params":{"weights":{"arm-a":0.5,"arm-b":0.5}}}'

uv run python apps/cli/main.py add-arms \
  --workspace-id ws-demo \
  --job-id job_123 \
  --arms '[{"arm_id":"arm-a","name":"A","arm_type":"artifact","payload_ref":"file://a","metadata":{}},{"arm_id":"arm-b","name":"B","arm_type":"artifact","payload_ref":"file://b","metadata":{}}]'

uv run python apps/cli/main.py assign \
  --workspace-id ws-demo \
  --job-id job_123 \
  --unit-id visitor-42 \
  --idempotency-key req-42 \
  --candidate-arms '["arm-a","arm-b"]' \
  --context '{"country":"US"}'
```

## Notes

- Complex nested fields are passed as JSON strings to keep command surface explicit.
- CLI prints JSON responses directly for easy piping or scripting.
