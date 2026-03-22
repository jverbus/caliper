# Email Webhook and Outcome Ingest

Chunk: **P7-002 Email webhook and outcome ingest**

## What this adds

The email adapter now supports webhook-event ingest and mapping into Caliper outcomes with duplicate-safe handling.

### Supported webhook mappings

`EmailWebhookType` values map to outcome metrics:

- `open` -> `email_open`
- `click` -> `email_click`
- `conversion` -> `email_conversion`
- `reply` -> `email_reply`
- `unsubscribe` -> `email_unsubscribe`
- `complaint` -> `email_complaint`

Each webhook event is written through `log_outcome` as a single `OutcomeEvent` tied to the original `decision_id`.

## Delayed outcomes

Webhook events carry an explicit `occurred_at` timestamp, which is used as the outcome event timestamp. This supports delayed opens/clicks/conversions/replies that can arrive long after send time.

The adapter also sets a configurable attribution window (`outcome_attribution_window_hours`, default `168` hours / 7 days).

## Idempotent webhook handling

`EmailAdapter.ingest_webhook()` tracks processed `webhook_event_id` values and drops duplicates (`None` return on replay). For accepted events, webhook identity is also persisted in outcome metadata:

- `source: email_webhook`
- `surface: email`
- `webhook_event_id`
- `webhook_type`

This keeps duplicate webhook deliveries safe while preserving payload context for auditing and guardrail derivation.

## Guardrail metric derivation

Because unsubscribe and complaint are emitted as explicit outcome metrics (`email_unsubscribe`, `email_complaint`), guardrail logic can derive safety metrics directly from ingested webhook outcomes.
