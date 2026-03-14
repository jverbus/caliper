# P7-001 Email adapter core

## Scope

`caliper_adapters.email.EmailAdapter` provides the first email-surface integration layer:

- recipient-ID ingestion for a tranche
- request-time assignment per recipient
- explicit send-plan representation
- provider handoff abstraction (simulator or pluggable ESP)
- executed exposure logging for successfully delivered sends

## API surface

- `EmailRecipient`: recipient identifier + optional address + per-recipient context
- `EmailSendInstruction`: per-recipient assignment envelope with decision + arm details
- `EmailSendPlan`: immutable tranche plan with generated timestamp + instructions
- `EmailDeliveryProvider`: protocol for simulator/ESP delivery providers
- `EmailAdapter.build_send_plan(...)`: assignment pass for an email tranche
- `EmailAdapter.dispatch_send_plan(...)`: provider handoff + executed exposure logging

## Behavior details

### Tranche assignment

`build_send_plan(...)` issues one `AssignRequest` per recipient, with deterministic idempotency keys:

`{idempotency_prefix}:{tranche_id}:{recipient_id}`

Campaign context and recipient context are merged into assignment context.

### Send-plan handoff and delivery recording

`dispatch_send_plan(...)` calls `provider.deliver(plan)` and expects a structured `DeliveryResult`.
For each delivered record, the adapter emits an executed exposure event with metadata:

- `surface=email`
- `tranche_id`
- `provider`
- `provider_message_id`

Failed delivery records are preserved in the returned `DeliveryResult` but do not emit executed exposures.

## Acceptance mapping

- **Recipient import / recipient-ID ingestion:** `EmailRecipient` list is the direct ingestion contract.
- **Assignment for send tranche:** `build_send_plan(...)` assigns each recipient in the tranche.
- **Send-plan representation:** `EmailSendPlan` + `EmailSendInstruction` encode deterministic send intent.
- **Handoff to simulator/pluggable ESP:** `EmailDeliveryProvider` protocol + `dispatch_send_plan(...)` implement provider-agnostic handoff.
