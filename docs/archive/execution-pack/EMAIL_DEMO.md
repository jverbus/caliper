# P7-004 Email demo

Chunk: **P7-004 Email demo**

## Scope

`examples/email_demo/demo.py` now provides an end-to-end email-surface demo in both embedded and service mode:

- Creates an email job with guardrails and adaptive policy settings
- Registers two email subject-line arms
- Plans and dispatches two send tranches through `EmailTranchePlanner`
- Logs delayed webhook outcomes (open/click/conversion/unsubscribe)
- Runs worker policy-update tasks between tranches to trigger guardrail actions
- Generates deterministic report artifacts (`json`, `md`, `html`)

## Demo behavior

### Tranche loop

The demo runs two tranches:

1. **Tranche 1** assigns across both active arms.
2. Webhook outcomes are ingested with delayed timestamps.
3. A worker policy-update task executes and evaluates guardrails.
4. An unsubscribe breach triggers a cap action on the offending arm.
5. **Tranche 2** plans using refreshed active arms, demonstrating reallocation.

### Guardrail and delayed outcomes

- Guardrail rule: `email_unsubscribe > 0.2` with `cap` action.
- Outcome timestamps intentionally include delayed events (24h+ after send) to reflect realistic email webhook lag.
- Generated reports include guardrail event rows for safety visibility.

## Commands

```bash
# Embedded mode
make demo-email

# Service mode (API running separately)
PYTHONPATH=packages/py-caliper-core/src:packages/py-caliper-storage/src:packages/py-caliper-events/src:packages/py-caliper-policies/src:packages/py-caliper-reward/src:packages/py-caliper-reports/src:packages/py-caliper-adapters/src:packages/py-sdk/src:apps \
  uv run python examples/email_demo/demo.py --mode service --db-url sqlite:///./data/email-demo-service.db
```

## Artifact output

Default artifact locations:

- `docs/fixtures/email_demo/embedded/`
- `docs/fixtures/email_demo/service/`

Each output directory contains:

- `report.json`
- `report.md`
- `report.html`

## Acceptance mapping

- **`examples/email_demo`**: Implemented with full end-to-end flow.
- **`make demo-email`**: Runs embedded email demo entrypoint.
- **Sample email campaign report**: Fixtures generated and checked in.
- **Demo runs end to end**: Covered by integration tests in embedded and service mode.
- **Report includes guardrail behavior + delayed outcomes**: guardrail event presence and delayed webhook ingest are explicitly exercised and asserted.
