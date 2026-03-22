# Adapters and Surfaces Spec

This document defines how Caliper interacts with real execution surfaces.

## 1. Adapter purpose

Adapters let Caliper serve as a broad optimization layer rather than a surface-specific tool.

V1 adapters must exist for:

- workflow execution,
- web experiences,
- email campaigns.

Organization routing is modeled in the schema now and deferred in runtime.

## 2. Shared adapter contract

Every adapter must support the following logical steps:

1. capture an opportunity,
2. call assignment or embedded runtime,
3. execute or render the chosen arm,
4. log exposure only when the arm was actually used,
5. log outcomes asynchronously when they occur,
6. preserve idempotency and identity across retries.

Adapters must not implement policy logic.

## 3. Common adapter requirements

Every adapter must propagate:

- `workspace_id`
- `job_id`
- `decision_id`
- `unit_id`
- adapter-specific external IDs
- idempotency key where applicable

Every adapter must also support:

- retries,
- configurable timeouts,
- structured error handling,
- deferred outcome arrival,
- field redaction where needed.

## 4. Workflow adapter

### 4.1 Why it comes first

Workflow optimization is the fastest surface for proving the core platform because:

- it works well in embedded mode,
- it avoids remote rendering concerns,
- it exposes cost, latency, and quality naturally,
- it maps cleanly to agentic work.

### 4.2 Responsibilities

- request assignment before workflow execution,
- dispatch to the chosen workflow arm,
- log execution start and completion if useful,
- log cost, latency, and quality or acceptance outcomes,
- support human-review insertion as an outcome event.

### 4.3 Example arms

- prompt chain A
- prompt chain B
- tool order variant C
- review-required workflow D

## 5. Web adapter

### 5.1 Responsibilities

- request assignment on incoming request or page selection boundary,
- render the chosen artifact or variant,
- log exposure when rendering actually happened,
- log click and conversion outcomes later,
- handle candidate-arm subsets if the page only supports some variants.

### 5.2 Supported integration patterns

Pattern A: same process or same service deployment  
Pattern B: remote site calling shared-service Caliper  
Pattern C: hosted site calling a reachable local Caliper instance

Pattern C only works if networking allows it. Caliper does not need to ship tunneling in v1.

### 5.3 Identity guidance

Suggested unit IDs:

- session ID
- visitor ID
- request-scoped user bucket
- experiment cookie or durable anonymous ID

Use hashed or bucketed IDs where privacy policy requires it.

## 6. Email adapter

### 6.1 Responsibilities

- assign recipient or tranche to an arm before send,
- hand off send execution to an ESP or simulator,
- ingest opens, clicks, conversions, unsubscribes, and complaints,
- support delayed attribution windows,
- support tranche-by-tranche reallocation.

### 6.2 Why email is different

Email is not request-time serving. It is campaign-time allocation with delayed outcomes.

Therefore the adapter must support:

- batch recipient import,
- tranche plans,
- deferred webhook ingestion,
- update cadence tied to send windows or thresholds.

### 6.3 Recommended v1 pattern

1. register job and arms
2. import recipient list or recipient IDs
3. assign first tranche
4. send via existing ESP or simulator
5. ingest early outcomes
6. update policy
7. assign next tranche
8. repeat until campaign complete

### 6.4 Email guardrails

The email adapter must elevate these signals prominently:

- unsubscribe rate,
- spam complaint rate,
- bounce rate if available,
- send failure rate.

Guardrail breaches may:

- pause the whole job,
- cap an offending arm,
- require manual resume.

## 7. Org-router surface

V1 requirement:

- support `arm_type = organization` in the domain model
- support `surface_type = org_router` in the schema
- do not build the recursive runtime in v1

Post-v1 target:

- choose a cluster or topology,
- optionally invoke a child workflow policy,
- compare quality, speed, and cost by organization.

## 8. Payload reference rules

Arms should not have to inline the full artifact or workflow definition in every API request.

`payload_ref` may point to:

- a local filesystem path,
- a URL,
- an adapter-managed key,
- a database row,
- an application-specific object ID.

The adapter is responsible for resolving payloads at execution time where necessary.

## 9. Idempotency rules by surface

### Workflow

Use task or request ID plus attempt number as needed.

### Web

Use request ID or deterministic assignment key tied to the chosen assignment boundary.

### Email

Use recipient ID plus campaign tranche plus send attempt.

## 10. Surface-specific acceptance targets

### Workflow

- supports at least 3 arms
- logs cost and latency
- can include a human acceptance outcome
- works in embedded mode and service mode

### Web

- supports at least 2 to 10 arms in demo
- logs exposure on actual render
- logs click and conversion
- supports remote HTTP use

### Email

- supports at least 10 to 50 arms in demo or simulator
- reallocates between tranches
- logs unsubscribe and complaint guardrails
- supports delayed outcomes

## 11. Why adapters matter

Adapters are how Caliper stays broad.

If the adapter contract is done well, Caliper can optimize:

- websites,
- emails,
- prompt stacks,
- workflows,
- and eventually organizations,

without changing its core decision model.
