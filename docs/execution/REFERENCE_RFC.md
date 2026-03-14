# RFC-001: Caliper Adaptive Optimization Platform

**Status:** Draft  
**Owner:** Engineering / Platform  
**Last updated:** 2026-03-14  
**Related docs:** PRD - Caliper Adaptive Execution Layer

---

## 1. Executive summary

Caliper should not be built as “a bandit library with a dashboard.” It should be built as an **adaptive decision and measurement platform** for autonomous work. Agents, workflows, websites, emails, and organizational clusters should all use the same substrate:

1. define an optimization job,
2. register candidate arms,
3. assign traffic or work with a policy,
4. log the decision and its probability,
5. observe outcomes and costs,
6. update policy,
7. report what changed.

### Core recommendation

We should **own the platform layer** and **selectively use external libraries**:

- **Build in-house**
  - control plane
  - event ledger
  - reward / objective engine
  - assignment API
  - adapter SDKs
  - reporting
  - guardrails
  - simple bandits: random, fixed split, epsilon-greedy, UCB1, Thompson sampling
  - one transparent contextual baseline if desired (disjoint LinUCB)

- **Use external libraries behind our interface**
  - **Vowpal Wabbit (VW)** for richer contextual bandits, especially action-dependent features and variable action sets
  - **Open Bandit Pipeline (OBP)** for off-policy evaluation and offline benchmarking
  - **MABWiser** and/or **contextualbandits** for prototyping, benchmarking, and simulation, not as the long-term product surface

### Why

The hard part of Caliper is not just choosing an arm. The hard part is:

- representing jobs, arms, and segments,
- logging decisions with propensities,
- handling delayed outcomes,
- supporting multiple execution surfaces,
- enforcing guardrails,
- computing objective functions,
- explaining decisions,
- replaying and evaluating policies,
- producing trustworthy morning reports.

Public libraries help with the model. They do **not** solve the platform.

### Recommended build order

1. PRD first - define product boundaries, target users, core use cases, and success metrics.
2. RFC second - define the technical architecture that satisfies the PRD.
3. In practice, draft them in parallel, but the PRD should be the controlling document.

---

## 2. Problem statement

OpenClaw can generate many candidate actions: copy variants, websites, prompts, workflows, or agent team structures. What is missing is the platform that can:

- serve those variants in the real world,
- measure success consistently,
- allocate traffic adaptively,
- learn from feedback,
- and report results in an operationally trustworthy way.

Today, most experimentation tooling is too narrow:

- classic A/B tooling is page- or product-focused,
- email tools optimize campaigns but not arbitrary workflows,
- model-eval tooling is AI-centric and disconnected from business outcomes,
- ML libraries optimize a policy but do not manage approvals, guardrails, or operational reporting.

Caliper should fill that gap.

---

## 3. Goals

### 3.1 Product goals supported by this RFC

Caliper must support the following top-level use cases with the same platform primitives:

1. **Artifact optimization**
   - website variants
   - landing pages
   - email subject lines and bodies
   - ads / CTAs / copy

2. **Workflow optimization**
   - prompt chains
   - tool order
   - agent review steps
   - retrieval strategies
   - send timing / sequencing

3. **Organization optimization**
   - which cluster of agents should receive a task
   - which team topology performs best
   - whether human review should be inserted
   - which operating mode balances quality, speed, and cost best

### 3.2 Technical goals

- Unify A/B tests, bandits, and contextual bandits under one control plane.
- Support real-time decisioning and delayed outcomes.
- Preserve auditability through append-only event logging.
- Make policies replaceable behind a stable internal interface.
- Provide strong offline evaluation support before risky launches.
- Keep the first version simple enough to ship without overfitting to a single surface.

---

## 4. Non-goals

These are explicitly out of scope for the first architecture.

- full reinforcement learning beyond one-step decision problems
- multi-slot slate optimization as a first-class runtime primitive
- neural bandits as the default baseline
- generic feature store platform adoption in v1
- full warehouse-native product design
- end-user visual website builder
- full ESP replacement or CDP replacement
- agent framework lock-in

We can add some of these later, but not in the initial repo.

---

## 5. Build vs buy: recommendation

### 5.1 Short answer

**Do not write the whole bandit stack from scratch.**  
**Do write your own platform abstraction and own the simple policies.**

### 5.2 What to build ourselves

We should own the following because they are core product IP and must fit our domain exactly:

- optimization job schema
- arm lifecycle management
- assignment API and SDK contracts
- exposure / outcome logging
- reward calculation
- guardrails and constraints
- reporting and explainability
- job state machine
- approval / rollback / pause controls
- hierarchical routing abstraction
- multi-surface adapters
- basic bandit policies for transparent operation

### 5.3 What to use from public libraries

#### Vowpal Wabbit
Use as the primary external contextual bandit engine when:

- context matters,
- exploration must be explicit,
- the action set can change by request,
- or each action has its own features.

VW is the best fit for the “website/email/workflow variants with context” direction because it supports contextual bandit learning and exploration, including `--cb_explore_adf` for cases where available actions change over time or each action has rich action-specific information.

#### Open Bandit Pipeline (OBP)
Use for:

- offline policy evaluation (IPS, SNIPS, DR-style workflows)
- replay experiments
- policy comparison before live rollout
- simulation and benchmarking against logged bandit feedback

OBP is not your serving engine. It is your safety and research harness.

#### MABWiser
Use for:

- quick prototyping
- baseline simulations
- internal algorithm comparisons
- reference implementations when validating your own simple policies

It is a strong prototyping library, but it should not define the Caliper runtime interface.

#### contextualbandits
Use only if you want a second research sandbox for online contextual methods and comparisons. It is useful for experimentation but should not be the product dependency that defines runtime behavior.

### 5.4 Explicit recommendation matrix

| Capability | Own | External | Notes |
|---|---:|---:|---|
| Control plane | Yes | No | Core product |
| Assignment API | Yes | No | Core product |
| Event schemas / ledger | Yes | No | Core product |
| Reward / guardrails | Yes | No | Core product |
| Reporting | Yes | No | Core product |
| Random / A/B / epsilon / UCB / TS | Yes | Optional reference only | Easy to own |
| Disjoint LinUCB | Yes, optional | Optional reference only | Good transparent baseline |
| Action-dependent contextual bandits | No | Yes (VW) | Better to wrap than re-invent early |
| Off-policy evaluation | Partial wrapper | Yes (OBP, VW estimators) | Keep interface ours |
| Simulation | Partial | Yes | Use external tooling heavily |

### 5.5 Why not fully depend on one library

Because the product surface is broader than a learning algorithm:

- decisions may target web, email, prompts, workflows, or agent clusters,
- objectives combine reward, cost, latency, and risk,
- traffic may be constrained by approvals or quotas,
- outcomes can be delayed or partial,
- jobs need pausing, rollback, and reporting,
- users need confidence intervals, not just scores,
- policies will eventually be hierarchical.

A library can be a model backend. It should not be the architecture.

---

## 6. External library evaluation

### 6.1 Vowpal Wabbit

**Use for:** production contextual bandits, especially with variable action sets.

**Strengths**

- contextual bandit focus
- explicit support for exploration strategies
- support for different contextual bandit estimation / evaluation approaches
- support for action-dependent features
- strong performance orientation

**Weaknesses**

- awkward data formatting compared with native Python APIs
- steeper operator learning curve
- less natural for app engineers who want clean domain objects

**Conclusion**

Wrap VW behind a Caliper `PolicyBackend` interface. Do not leak VW types or CLI flags across the codebase.

### 6.2 OBP

**Use for:** offline evaluation, replay, and policy validation.

**Strengths**

- standardized OPE workflows
- good for comparing policies on logged data
- useful for build-time safety checks and release gates

**Weaknesses**

- not a serving layer
- not a full product runtime

**Conclusion**

Make OBP part of the offline evaluation package and CI / notebook workflow, not the online decision path.

### 6.3 MABWiser

**Use for:** reference, simulation, and prototyping.

**Strengths**

- clean scikit-style API
- easy to prototype and compare simple policies
- useful for validating assumptions quickly

**Weaknesses**

- research-oriented rather than platform-oriented
- not the best fit for dynamic-action production serving

**Conclusion**

Good internal tool. Not the product contract.

### 6.4 contextualbandits

**Use for:** sandbox experiments if the team wants broad algorithm coverage.

**Strengths**

- many contextual algorithms
- useful research surface

**Weaknesses**

- compiled dependency chain adds friction
- not ideal as a product dependency surface

**Conclusion**

Optional research package only.

### 6.5 RLlib

**Recommendation:** do not use as the first repo foundation.

Reasons:

- broader RL framework than we need
- more moving parts than a bandit-focused product requires
- likely overkill for one-step decisioning and logging-heavy experimentation

---

## 7. Architecture overview

### 7.1 Core idea

The architecture revolves around the following primitives:

- `OptimizationJob`
- `Arm`
- `Policy`
- `Decision`
- `Exposure`
- `Outcome`
- `Guardrail`
- `Report`
- `Cluster`

### 7.2 High-level flow

```text
OpenClaw / human operator
    -> create OptimizationJob
    -> register arms
    -> deploy via adapter

Runtime request
    -> Assignment API
    -> Policy engine chooses arm and probability
    -> Decision logged
    -> adapter executes / serves chosen arm
    -> exposures and outcomes logged
    -> reward engine computes signals
    -> policy updater learns / rebalances
    -> report engine summarizes changes
```

### 7.3 Service topology

```text
[UI / CLI / SDKs]
        |
        v
[Control Plane API] ---- [Postgres]
        |
        +---- [Assignment Service] ---- [Redis cache]
        |
        +---- [Temporal Workers / Job Orchestrator]
        |
        +---- [Policy Trainer / Updater]
        |
        +---- [Event Ingest API] ---- [Kafka/Redpanda optional] ---- [ClickHouse]
        |
        +---- [Report Generator] ---- [Object store / Parquet]
```

### 7.4 Storage split

- **Postgres** for transactional state
  - jobs
  - arms
  - policies
  - approvals
  - schedules
  - report metadata

- **ClickHouse** for event and outcome analytics
  - decisions
  - exposures
  - outcomes
  - costs
  - segment aggregates
  - time-window rollups

- **Redis** for hot caches
  - current job config
  - compiled policy params
  - assignment caches where necessary

- **Object storage + Parquet** for offline datasets
  - training snapshots
  - replay datasets
  - daily reports
  - archive logs

---

## 8. Recommended tech stack

### 8.1 Language strategy

Use a **polyglot-but-minimal** stack:

- **Python** for policy logic, analytics, OPE, workers, and most backend services
- **TypeScript** for UI, web/email/agent SDKs, and integration surfaces

Do **not** start with Go or Rust as the primary stack unless you already know you need ultra-low-latency hot-path serving. You can always split out the assignment service later.

### 8.2 Monorepo strategy

Use a monorepo with clearly separated apps and packages.

**Recommended tooling**

- Python package/dependency management: `uv`
- lint/format/type-check: `ruff`, `mypy`
- tests: `pytest`, `hypothesis`
- TypeScript workspace: `pnpm`
- frontend: `Next.js`
- backend API: `FastAPI`
- async jobs / orchestration: `Temporal`
- DB access: `SQLAlchemy` + Alembic
- schemas: `Pydantic v2` or `msgspec` for runtime schemas; JSON Schema / OpenAPI for SDK contracts

### 8.3 Data / infrastructure stack

| Layer | Recommendation | Why |
|---|---|---|
| OLTP state | PostgreSQL | strong relational core, JSONB for flexible config, partitioning available |
| analytics | ClickHouse | excellent fit for event-heavy near-real-time analytics |
| cache | Redis | low-latency lookups, feature caching |
| workflows | Temporal | durable long-running orchestration |
| queue / stream | Kafka or Redpanda when scale requires | decouple ingest and analytics |
| object storage | S3-compatible + Parquet | offline training and report datasets |
| local analytics | DuckDB | fast embedded analysis on Parquet |

### 8.4 Why this stack fits Caliper

- Postgres gives structured ownership and migration discipline.
- ClickHouse gives event-scale analytical querying and near-real-time rollups.
- Temporal fits long-running campaign jobs, delayed outcomes, and scheduled morning reports.
- Kafka/Redpanda is optional at first, but becomes important when ingest volume or adapter count grows.
- Python keeps the policy layer close to the ML/OPE ecosystem.
- TypeScript keeps SDKs and integration surfaces ergonomic.

### 8.5 Leaner v1 stack if team size is small

If you want the smallest viable first deployment:

- FastAPI
- Postgres
- Redis
- ClickHouse
- Temporal
- Next.js

Skip Kafka initially. Add it only when ingest pressure or decoupling needs justify it.

---

## 9. New repo structure

```text
caliper/
  apps/
    api/                    # FastAPI control-plane API
    assign/                 # low-latency assignment service
    ingest/                 # event ingest API
    worker/                 # Temporal workers, report jobs, batch updaters
    ui/                     # Next.js operator console

  packages/
    py-caliper-core/        # domain models, shared config, utilities
    py-caliper-policies/    # random/A-B/UCB/TS/LinUCB/VW adapters
    py-caliper-ope/         # offline evaluation, replay, confidence estimates
    py-caliper-reward/      # reward/objective and guardrail computation
    py-caliper-adapters/    # web, email, workflow, org-router adapters
    py-caliper-reports/     # report generation and export logic
    ts-sdk/                 # JS/TS client SDK
    py-sdk/                 # Python client SDK
    schemas/                # JSON Schemas / OpenAPI / protobuf definitions

  infra/
    docker/
    terraform/
    k8s/

  docs/
    prd/
    rfc/
    runbooks/

  notebooks/
    simulations/
    replay/
    benchmarks/

  tests/
    integration/
    load/
    replay/
```

### 9.1 Package ownership rules

- `py-caliper-core` must not depend on app packages.
- `py-caliper-policies` can depend on `core` and `schemas`, never on UI.
- SDKs should use generated schemas, not duplicate model definitions.
- Policy backends must be swappable.

---

## 10. Domain model

### 10.1 OptimizationJob

Represents a unit of optimization.

Fields:

- `job_id`
- `workspace_id`
- `name`
- `surface_type` (`web`, `email`, `workflow`, `org_router`, `generic`)
- `status` (`draft`, `shadow`, `active`, `paused`, `completed`, `archived`)
- `objective_spec`
- `guardrail_spec`
- `policy_spec`
- `arm_ids`
- `segment_spec`
- `schedule_spec`
- `approval_state`
- `created_by`
- `created_at`
- `updated_at`

### 10.2 Arm

Represents any candidate way of acting.

Fields:

- `arm_id`
- `job_id`
- `arm_type` (`artifact`, `workflow`, `organization`)
- `name`
- `payload_ref`
- `metadata`
- `state` (`draft`, `eligible`, `held_out`, `paused`, `retired`)
- `constraints`
- `created_at`

### 10.3 PolicySpec

Defines how assignment happens.

Fields:

- `policy_family`
  - `fixed_split`
  - `epsilon_greedy`
  - `ucb1`
  - `thompson_sampling`
  - `linucb`
  - `vw_cb_adf`
  - `hierarchical_router`
- `params`
- `exploration_rules`
- `warm_start_rules`
- `min_traffic_rules`
- `update_cadence`
- `context_schema_version`
- `policy_version`

### 10.4 Decision

The canonical assignment record.

Fields:

- `decision_id`
- `job_id`
- `arm_id`
- `policy_version`
- `unit_id`
- `request_context`
- `arm_features`
- `scores`
- `propensity`
- `decision_reason`
- `timestamp`

### 10.5 Exposure

Represents whether the assigned arm was actually shown or executed.

Fields:

- `exposure_id`
- `decision_id`
- `exposure_type`
- `timestamp`
- `metadata`

### 10.6 Outcome

Represents observed reward or supporting signal.

Fields:

- `outcome_id`
- `decision_id`
- `outcome_type`
- `value`
- `timestamp`
- `attribution_window`
- `metadata`

### 10.7 GuardrailEvent

Fields:

- `guardrail_event_id`
- `job_id`
- `decision_id` optional
- `guardrail_name`
- `severity`
- `measured_value`
- `threshold`
- `timestamp`

---

## 11. Event contracts

### 11.1 Why the event model matters

Contextual bandits live or die on logging quality. If we do not log the chosen action, context, and probability of choosing that action, we lose the ability to do sound replay and off-policy evaluation.

### 11.2 Canonical event types

- `decision.assigned`
- `decision.exposed`
- `execution.started`
- `execution.completed`
- `outcome.observed`
- `cost.observed`
- `guardrail.triggered`
- `policy.updated`
- `report.generated`

### 11.3 Minimum required decision envelope

```json
{
  "decision_id": "dec_123",
  "workspace_id": "ws_1",
  "job_id": "job_42",
  "unit_id": "user_abc",
  "candidate_arms": ["a1", "a2", "a3"],
  "chosen_arm": "a2",
  "propensity": 0.24,
  "policy_family": "vw_cb_adf",
  "policy_version": "2026-03-14.1",
  "context_schema_version": "ctx_v3",
  "context": {...},
  "arm_features": {...},
  "timestamp": "2026-03-14T08:00:00Z"
}
```

### 11.4 Logging rules

1. Every live decision must emit a `decision.assigned` event.
2. Every live decision should include a valid propensity.
3. `decision.exposed` must be separate from `decision.assigned` for cases where assignment does not result in an actual exposure.
4. Reward events must be append-only.
5. Mutable state is derived from events, not vice versa.

---

## 12. Policy abstraction

### 12.1 Core interface

```python
class Policy(Protocol):
    def choose(self, request: DecisionRequest) -> DecisionResult: ...
    def update(self, batch: list[OutcomeRecord]) -> UpdateResult: ...
    def snapshot(self) -> PolicySnapshot: ...
    def validate(self) -> list[ValidationIssue]: ...
```

### 12.2 Required properties of every policy

Each policy implementation must:

- return an arm and a probability
- be versioned
- emit auditable metadata
- support deterministic replay mode
- expose diagnostics
- support warm start / cold start behavior
- support arm retirement and addition

### 12.3 Built-in policy families for v1

- fixed split A/B/n
- epsilon-greedy
- UCB1
- Thompson sampling (Beta-Bernoulli and Gaussian variants where appropriate)
- successive-halving / elimination controller
- optional disjoint LinUCB baseline

### 12.4 Why own these policies

These are simple enough to understand, test, and explain. Owning them reduces operational opacity and eliminates unnecessary runtime dependencies.

---

## 13. Contextual bandits: difficulty and implementation plan

### 13.1 How hard is contextual bandits?

**Algorithmically:** moderate.  
**Operationally:** high.

The math for a first contextual bandit is not the hard part. The hard parts are:

- reliable feature extraction at decision time
- stable feature versioning
- action-set representation
- explicit exploration and propensity logging
- delayed rewards
- outcome attribution windows
- replay and OPE
- non-stationarity and drift
- keeping behavior interpretable enough for operators

### 13.2 What makes it harder than standard bandits

Standard bandits mainly track arm-level reward estimates. Contextual bandits require:

- a context vector or structured context object,
- sometimes per-arm feature vectors,
- a policy that conditions on context,
- training and serving consistency,
- and logging the action probability under the behavior policy.

### 13.3 Recommended rollout sequence

#### Phase A - contextual-ready schema only

Before implementing any contextual learner, add support for:

- `context_schema_version`
- request context payloads
- candidate arm sets per request
- propensity logging
- replay export format

This is mandatory even if the runtime still uses non-contextual bandits.

#### Phase B - simple contextual baseline

Implement one of the following in-house:

- **Disjoint LinUCB** if rewards are roughly linear and interpretability matters
- **Contextual Thompson via regression wrappers** only if the team is already comfortable with it

Recommendation: **start with Disjoint LinUCB**.

Why:

- conceptually understandable
- easy to inspect scores
- good baseline for segment-aware allocation
- manageable implementation burden

#### Phase C - richer contextual backend

Add a VW adapter for:

- dynamic action sets
- per-action features
- exploration algorithms beyond your first in-house baseline
- more scalable contextual experimentation

#### Phase D - contextual OPE gates

Before allowing broad auto-promotion of contextual policies, require:

- replay evaluation
- OPE checks
- guardrail risk thresholds
- shadow mode on live traffic

### 13.4 Fixed-arm vs variable-arm contextual problems

#### Fixed-arm contextual bandit

Use when:

- the arm set is small and stable
- e.g. 5 subject lines or 10 workflows

This is the easiest contextual step.

#### Action-dependent / variable-arm contextual bandit

Use when:

- each request can have a different arm set,
- or each arm has distinct features,
- e.g. candidate articles, generated website variants, dynamic workflow choices.

This is where VW is especially useful.

### 13.5 Context design requirements

All contextual policies should depend on a versioned feature contract:

```yaml
context_schema:
  version: ctx_v1
  shared_features:
    - tenant_id_hash
    - channel
    - geo_bucket
    - hour_of_day
    - user_segment
    - device_type
  arm_features:
    - arm_type
    - variant_length
    - send_time_bucket
    - cost_estimate
```

Rules:

- no raw PII in the policy payload
- features must be reproducible offline
- features must be logged or derivable
- missing-value behavior must be deterministic

### 13.6 Online update strategy

Prefer **micro-batch updates** first, not per-event online updates.

Why:

- simpler rollback
- easier debugging
- better reproducibility
- easier batch OPE checks

Recommended initial cadence:

- non-contextual policies: frequent incremental updates allowed
- contextual policies: periodic micro-batch retraining with versioned snapshots

### 13.7 Promotion rules for contextual policies

A contextual policy should only be promotable if:

- context coverage is adequate,
- no critical feature drift is detected,
- OPE or replay checks pass,
- propensities are valid,
- guardrail estimates are within limits,
- and live shadow comparisons are directionally consistent.

---

## 14. Assignment API

### 14.1 Decision request

```json
{
  "workspace_id": "ws_1",
  "job_id": "job_42",
  "unit_id": "recipient_123",
  "candidate_arms": ["arm_a", "arm_b", "arm_c"],
  "context": {
    "segment": "enterprise",
    "hour_of_day": 9,
    "country": "US"
  }
}
```

### 14.2 Decision response

```json
{
  "decision_id": "dec_123",
  "job_id": "job_42",
  "arm_id": "arm_b",
  "propensity": 0.31,
  "policy_family": "linucb",
  "policy_version": "2026-03-14.1",
  "diagnostics": {
    "scores": {
      "arm_a": 0.52,
      "arm_b": 0.57,
      "arm_c": 0.49
    },
    "reason": "highest_ucb"
  }
}
```

### 14.3 Exposure API

The adapter must call an exposure endpoint only when the decision was actually used.

### 14.4 Outcome API

Outcomes should support:

- binary reward
- numeric reward
- cost
- latency
- custom named events
- delayed attribution windows

---

## 15. Reward and guardrail engine

### 15.1 Objective model

Caliper must not hardcode CTR as the objective.

Each job should define:

- primary reward
- optional secondary metrics
- penalties
- hard guardrails

Example:

```yaml
objective:
  reward:
    formula: 1.0 * signup + 0.2 * qualified_demo
  penalties:
    - 0.05 * token_cost_usd
    - 0.02 * p95_latency_seconds
  guardrails:
    - unsubscribe_rate < 0.004
    - spam_complaint_rate < 0.001
    - error_rate < 0.01
```

### 15.2 Reward engine responsibilities

- normalize raw outcomes
- compute delayed rewards
- join costs to decisions
- compute job-level and segment-level metrics
- produce update-ready training sets

### 15.3 Guardrail actions

If guardrails breach:

- pause job,
- cap traffic,
- demote affected arms,
- require manual approval,
- annotate morning report.

---

## 16. Offline policy evaluation and replay

### 16.1 Why OPE is mandatory

Contextual policies become risky if we can only evaluate them live. We need a disciplined pre-launch workflow.

### 16.2 Minimum OPE workflow

1. export logged data with context, chosen action, propensity, reward
2. define candidate policy
3. estimate candidate performance with multiple estimators
4. compare against current behavior policy
5. inspect confidence intervals and support / overlap issues
6. only then allow shadow or small live ramp

### 16.3 Package responsibilities

- `py-caliper-ope`
  - dataset export / import
  - replay harness
  - IPS / SNIPS / DR wrappers
  - confidence intervals
  - policy comparison summaries

### 16.4 Release gate for contextual policies

No contextual policy should move from `shadow` to `active` unless:

- propensities are non-null and valid,
- overlap diagnostics are acceptable,
- offline estimates do not indicate obvious regression,
- and shadow mode has no guardrail alerts.

---

## 17. Reporting architecture

### 17.1 Morning report requirements

Each active job should be able to emit a report that answers:

- what changed since the prior report,
- where traffic shifted,
- which arms are leading,
- which segments differ,
- whether guardrails were hit,
- whether promotion / pruning is recommended.

### 17.2 Report outputs

- HTML / app-native dashboard card
- JSON summary for agents
- PDF / shareable export optional later

### 17.3 Machine-readable report schema

```json
{
  "job_id": "job_42",
  "window": {"start": "...", "end": "..."},
  "leaders": [...],
  "traffic_shifts": [...],
  "guardrails": [...],
  "segment_findings": [...],
  "recommendations": [...]
}
```

---

## 18. Adapter architecture

### 18.1 Adapter contract

Every adapter must support:

- request / opportunity capture
- arm execution or rendering
- exposure logging
- outcome logging
- idempotent retries

### 18.2 First adapters

#### Web adapter

- server or edge request to assignment API
- render chosen arm
- emit view / click / conversion events

#### Email adapter

- pre-send assignment
- send batch tranche
- log opens / clicks / conversions / unsubscribes / complaints
- support tranche-by-tranche reallocation

#### Workflow adapter

- request assignment before execution
- choose workflow / prompt stack / review path
- log task success, latency, cost, and human acceptance

#### Org-router adapter

- choose cluster or topology
- cluster may run local sub-policy
- log task completion and downstream outcomes

---

## 19. Hierarchical routing

### 19.1 Why we need it

The long-term product should optimize not just which copy variant wins, but which cluster or organization should handle a class of work.

### 19.2 Model

```text
Top-level router policy
  -> chooses cluster / organization arm
      -> local policy chooses workflow arm
          -> local policy chooses artifact arm
```

### 19.3 Initial implementation guidance

Do not build a general recursive policy engine on day one.

Instead:

- represent clusters as a special `arm_type = organization`
- allow one child policy reference in metadata
- support at most two levels initially

That gets most of the value without excessive complexity.

---

## 20. Security, privacy, and compliance

### 20.1 Principles

- minimize PII in decision payloads
- prefer hashed or bucketed identifiers
- keep raw PII in adapter-owned systems where possible
- make context logging configurable by field
- support retention windows and deletion workflows

### 20.2 Auditability

Every decision should be reconstructible from:

- policy version
- context schema version
- chosen arm
- propensity
- time window
- update snapshot id

---

## 21. Reliability and operational requirements

### 21.1 Service requirements

- assignment path should be stateless and horizontally scalable
- policy snapshots should be immutable
- updates should be idempotent
- event ingestion should tolerate retries and duplicates
- reports should be reproducible from persisted data

### 21.2 Failure handling

- if assignment service cannot score, fall back to safe policy
- if policy snapshot missing, use last known good snapshot
- if outcome ingest delayed, training windows should remain watermark-based
- if guardrails fail, auto-cap or pause depending on severity

---

## 22. Testing strategy

### 22.1 Policy tests

- deterministic simulation tests
- edge cases for cold start and arm retirement
- probability normalization tests
- regret sanity checks
- replay consistency tests

### 22.2 Platform tests

- idempotent event ingest
- decision to exposure to outcome joins
- delayed reward attribution
- report correctness on fixed fixtures
- shadow vs active routing correctness

### 22.3 Contextual tests

- train/serve feature parity tests
- feature schema migration tests
- missing feature handling
- overlap diagnostics
- OPE fixture tests

---

## 23. Rollout plan

### Phase 0 - foundations

- repo setup
- schemas
- Postgres + ClickHouse + Redis + Temporal
- control plane
- assignment API
- append-only event model

### Phase 1 - non-contextual optimization

- fixed split
- epsilon-greedy
- UCB1
- Thompson sampling
- web and email adapters
- morning reports

### Phase 2 - contextual-ready platform

- context schemas
- propensity logging
- replay exports
- shadow mode
- OPE package integration

### Phase 3 - first contextual policy

- disjoint LinUCB baseline
- feature validation
- limited segment-aware jobs

### Phase 4 - VW backend

- action-dependent features
- variable action sets
- richer exploration

### Phase 5 - hierarchical routing

- org-router adapter
- cluster optimization
- child-policy support

---

## 24. Open questions

1. Should policy updates be purely micro-batch, or should some simple policies update online?
2. Should the assignment API expose raw arm scores to SDK callers, or keep them internal?
3. Do we need a dedicated feature service before contextual rollout, or can adapters compute features deterministically?
4. Should reports be warehouse-generated or application-generated in v1?
5. At what scale do we introduce Kafka/Redpanda instead of direct ingest to ClickHouse + Postgres metadata writes?

---

## 25. Final recommendations

1. **Write the platform, not the whole research stack.**
2. **Own the simple policies.**
3. **Implement contextual readiness before contextual learning.**
4. **Start contextual with disjoint LinUCB or another transparent baseline.**
5. **Wrap Vowpal Wabbit for generic contextual + action-dependent cases.**
6. **Use OBP for OPE and replay.**
7. **Use PRD-first sequencing; then lock the technical RFC.**

