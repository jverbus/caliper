# Product Requirements Document: Caliper Adaptive Execution Layer

**Status:** Draft  
**Owner:** Product  
**Last updated:** 2026-03-14  
**Related docs:** RFC-001 - Caliper Adaptive Optimization Platform

---

## 1. Product summary

Caliper is the adaptive decision layer for autonomous work.

It allows agents and operators to:

- generate many candidate ways of acting,
- route real traffic or work across them,
- measure business outcomes, cost, and risk,
- adapt allocation over time,
- and receive reports about what is working.

The product must work across multiple surfaces, not just “AI evals”:

- websites
- emails
- copy variants
- prompts and workflows
- tool chains
- clusters of agents
- organizational topologies

### Product thesis

Every agentic system will need a native optimization layer.

OpenClaw can create options. Caliper should decide:

- which option gets served,
- how much traffic each option gets,
- how success is measured,
- when traffic shifts,
- and how the results are reported.

---

## 2. Problem statement

Autonomous systems can generate many candidate actions, but they lack a general-purpose operating layer to learn which actions actually work in the real world.

Today, teams piece together separate systems for:

- A/B testing
- email campaign optimization
- growth experimentation
- LLM prompt evaluation
- workflow benchmarking
- routing among agent teams

These systems do not share:

- a common decision model,
- a common outcome model,
- a common reporting model,
- or a common operator experience.

As a result:

- experiments are narrow,
- learning does not transfer across surfaces,
- reporting is fragmented,
- and operators cannot simply ask a system to “generate variants, run them, adapt, and tell me what won.”

---

## 3. Vision

A user should be able to say:

- “Create this website, make 100 variants, serve them, adapt traffic, and report back tomorrow morning.”
- “Send 50 email variants to this list, use a bandit to shift toward winners, and keep unsubscribe rate below threshold.”
- “Try three agent team structures for onboarding and tell me which organization is best for quality per dollar.”

Caliper should make that possible with one product.

---

## 4. Product principles

1. **Native to autonomous work**  
   The product is built for agents and operator-driven automation, not retrofitted from generic analytics.

2. **Outcome-first**  
   Optimize business and operational outcomes, not merely model scores.

3. **Broad, not AI-narrow**  
   Support content, workflows, and organizations with the same primitives.

4. **Adaptive by default**  
   A/B tests are supported, but bandits and adaptive routing are first-class.

5. **Safe to trust**  
   Reports must explain traffic shifts, confidence, and guardrail behavior.

6. **Composable**  
   External generators, surfaces, and agents can plug in through adapters and SDKs.

---

## 5. Target users

### 5.1 Primary users

#### A. Agent platform builder / technical founder

Needs to:

- integrate Caliper into agent products,
- define optimization jobs programmatically,
- set policies and guardrails,
- route work among candidate arms.

#### B. Growth / operations owner

Needs to:

- optimize campaigns and websites,
- review performance and risk,
- get a morning summary,
- promote winners and pause losing jobs.

#### C. Agent developer

Needs to:

- plug workflows into a bandit-ready interface,
- compare strategies,
- measure task success vs latency and cost,
- debug why a specific policy chose an arm.

### 5.2 Secondary users

#### D. Analyst / data scientist

Needs to:

- inspect job performance,
- run offline evaluation,
- compare policies,
- validate lift and guardrail behavior.

#### E. Executive / team lead

Needs to:

- understand what is improving,
- compare cluster or team structures,
- see reliable summaries of impact.

---

## 6. Jobs to be done

### Functional jobs

- When I have many variants, let me distribute traffic intelligently.
- When I want to optimize a workflow, let me compare multiple approaches on real outcomes.
- When I want to optimize an agent organization, let me compare clusters or topologies as first-class arms.
- When outcomes are delayed, keep attribution and reporting coherent.
- When I wake up, give me a report with the best actions and next recommendations.

### Emotional jobs

- Help me trust that automation is improving instead of drifting silently.
- Help me feel in control of adaptive systems.
- Help me explain outcomes to my team without manually stitching together dashboards.

---

## 7. Product scope

### 7.1 In scope for initial product

- optimization jobs
- arms / variants
- A/B/n and simple adaptive policies
- contextual-ready schema
- websites as a first-class surface
- emails as a first-class surface
- workflow / agent execution as a first-class surface
- reporting with morning summaries
- guardrails
- approvals / pause / rollback
- segment-aware analysis

### 7.2 In scope soon after v1

- contextual bandits
- action-dependent features
- org-router / cluster optimization
- offline policy evaluation workbench

### 7.3 Out of scope for initial release

- general-purpose data warehouse
- full agent builder platform
- deep RL beyond one-step decisions
- automated creative generation inside Caliper itself
- complete ESP or CMS replacement

---

## 8. Core concepts in the product

### Optimization Job

A named unit of optimization with:

- a surface
- a set of candidate arms
- an objective
- guardrails
- a policy
- a reporting cadence

### Arm

Any candidate way of acting:

- content variant
- workflow variant
- organization / cluster variant

### Policy

A traffic or routing rule:

- fixed split
- bandit
- contextual bandit
- hierarchical router

### Outcome

A measured result:

- conversion
- revenue
- click
- reply
- task success
- accepted deliverable
- latency
- cost
- unsubscribe rate

---

## 9. Primary use cases

### 9.1 Website optimization

**User story**  
As an operator, I want to create many page variants and have Caliper serve, measure, and adapt between them so that I can learn what converts best.

**Requirements**

- register 2 to 100+ variants
- serve variants to real traffic
- measure view, click, conversion, revenue, bounce, latency
- support screening + pruning + bandit allocation
- produce segment-level findings
- report winners and recommended promotion

### 9.2 Email campaign optimization

**User story**  
As a growth owner, I want to send multiple email variants to a large list, adapt traffic over time, and optimize for conversions while protecting unsubscribe and spam complaint rates.

**Requirements**

- batch or tranche-based sending
- arm assignment before send
- outcome tracking for open, click, conversion, unsubscribe, complaint
- adaptive allocation between tranches
- support delayed rewards
- report best overall and best by segment

### 9.3 Workflow optimization

**User story**  
As an agent developer, I want to compare prompt chains, tool sequences, and review workflows against real outcomes so I can improve quality per dollar.

**Requirements**

- route each task to a workflow arm
- log cost, latency, and quality outcomes
- support human review or acceptance as an outcome
- compare tradeoffs, not just a single metric

### 9.4 Organization / cluster optimization

**User story**  
As a platform owner, I want to compare clusters of agents or team structures as first-class arms so that I can learn which organization handles which work best.

**Requirements**

- allow an arm to represent a cluster or topology
- route work to clusters
- log cluster-level outcomes
- support two-level optimization: cluster first, local workflow second

---

## 10. Functional requirements

### 10.1 Job creation and management

The product must allow users or agents to:

- create a new optimization job
- define the surface type
- attach objective and guardrails
- attach reporting cadence
- add and retire arms
- pause, resume, or archive the job

**Acceptance criteria**

- jobs can be created by API and UI
- jobs have a stable lifecycle state machine
- jobs can be paused without data loss

### 10.2 Arm management

The product must allow users or agents to:

- register arms in bulk
- attach metadata and payload references
- label arms by type
- temporarily hold out or retire arms

**Acceptance criteria**

- one job supports at least 100 arms
- arm state changes are auditable

### 10.3 Policy configuration

The product must support:

- fixed split
- simple bandits
- contextual-ready schemas in v1
- contextual policies after rollout
- policy versioning and rollback

**Acceptance criteria**

- each decision can be tied to a policy version
- policy changes create audit records

### 10.4 Assignment / routing

The product must:

- choose an arm for each opportunity
- return a decision id and probability
- support per-request candidate arm lists
- support fallback policies when scoring is unavailable

**Acceptance criteria**

- decision id is joinable to all downstream events
- assignment is idempotent under retries where required

### 10.5 Measurement and outcome ingestion

The product must:

- ingest exposures and outcomes
- support binary, numeric, and named outcomes
- support delayed attribution windows
- support cost and latency signals

**Acceptance criteria**

- outcomes can arrive after assignment asynchronously
- operators can inspect raw and aggregated outcomes per job and arm

### 10.6 Reward and objective engine

The product must:

- allow a job to define a primary objective
- allow weighted secondary signals
- allow penalties and hard guardrails

**Acceptance criteria**

- objective configuration is stored with the job
- guardrails can auto-pause or cap traffic

### 10.7 Reporting

The product must generate reports that summarize:

- current leaders
- traffic shifts
- confidence / uncertainty language
- segment differences
- guardrail events
- recommended next actions

**Acceptance criteria**

- report can be generated manually and on schedule
- report exists in machine-readable and human-readable formats

### 10.8 Approvals and governance

The product must support:

- draft / shadow / active states
- optional approval before activation
- rollback to prior policy or prior arm set
- audit log of changes

### 10.9 SDKs and adapters

The product must provide:

- TypeScript SDK
- Python SDK
- web adapter
- email adapter
- workflow adapter

**Acceptance criteria**

- SDKs can create jobs, request decisions, and log outcomes
- adapters hide transport details from surface-specific code

---

## 11. User experience requirements

### 11.1 Create-and-launch flow

A user should be able to:

1. create an optimization job,
2. upload or register many arms,
3. define objective and guardrails,
4. choose policy,
5. preview rollout mode,
6. activate the job.

### 11.2 Monitor flow

A user should be able to see:

- live status
- traffic by arm
- key metrics by arm
- alerts and guardrail issues
- per-segment behavior
- policy version and last update

### 11.3 Morning report flow

A user should receive a report that clearly states:

- what improved,
- what regressed,
- what traffic shifted,
- whether the system recommends pruning or promotion,
- whether any guardrails are at risk.

### 11.4 Explainability

For any decision, the user should be able to inspect:

- chosen arm
- candidate arms
- policy family
- policy version
- recorded probability
- key context fields if permitted

---

## 12. Non-functional requirements

### 12.1 Reliability

- decisioning must be highly available
- event ingestion must tolerate retries and duplicates
- reports must be reproducible from stored data

### 12.2 Auditability

- every decision must have a stable identifier
- every job and policy change must be auditable
- every report must reference the exact data window and policy version(s)

### 12.3 Latency

- real-time serving surfaces must support low-latency arm selection
- non-real-time surfaces may use batch decisioning

### 12.4 Privacy and compliance

- minimize PII in decision payloads
- allow configurable field redaction / exclusion
- support retention and deletion policies

### 12.5 Extensibility

- new surfaces and policies should plug into existing primitives
- the system must not assume “copy optimization only”

---

## 13. Success metrics

### 13.1 Product adoption metrics

- number of active optimization jobs
- number of surfaces integrated
- number of decisions served per day
- percentage of jobs with scheduled reports enabled

### 13.2 Product value metrics

- median time from job creation to first live decision
- median time from launch to first trustworthy recommendation
- percentage of jobs producing measurable lift
- percentage of jobs with no manual analyst intervention required for first report

### 13.3 Platform quality metrics

- event join success rate from decision to outcome
- percentage of decisions with valid propensities logged
- report generation success rate
- percentage of jobs auto-paused correctly on guardrail breach

---

## 14. Release strategy

### Release 1 - Adaptive experimentation core

Includes:

- jobs
- arms
- fixed split and simple bandits
- web / email / workflow adapters
- reporting
- guardrails
- approvals

### Release 2 - Contextual readiness + shadow mode

Includes:

- context schemas
- propensity logging
- replay export
- offline evaluation surface
- shadow mode for candidate policies

### Release 3 - Contextual bandits

Includes:

- first contextual policy
- contextual policy diagnostics
- live contextual jobs with promotion rules

### Release 4 - Organization optimization

Includes:

- org-router / cluster arms
- two-level routing
- cluster-level reports and comparisons

---

## 15. Risks and mitigations

### Risk: product becomes “AI evals tool” instead of optimization layer

**Mitigation**

- define arms broadly
- define surfaces broadly
- support content, workflows, and organizations from the beginning

### Risk: contextual bandits create false confidence

**Mitigation**

- require propensities
- require shadow mode and OPE before broad rollout
- make uncertainty explicit in reporting

### Risk: users do not trust adaptive routing

**Mitigation**

- expose traffic shifts clearly
- expose guardrails and reasons
- support fixed-split fallback modes

### Risk: integrations are too narrow

**Mitigation**

- invest early in SDKs and adapters
- avoid hardcoding web-first assumptions into core concepts

### Risk: long-tail objectives become unmanageable

**Mitigation**

- use an explicit objective/guardrail schema
- start with weighted formulas and threshold rules

---

## 16. Open questions

1. Which surfaces should be called “tier-1” in the commercial story: web, email, workflow, or all three equally?
2. How opinionated should the product be about report recommendations versus simply presenting evidence?
3. Should users configure objective formulas directly, or should templates be the default UX?
4. Should cluster-of-agents optimization be visible in v1 messaging or reserved for later release positioning?

---

## 17. Recommendation on document order

The team should make the **PRD first**.

Reason:

- the biggest remaining questions are about product scope, positioning, and what counts as success,
- not about whether we can technically build a bandit service.

Once the PRD is accepted, the RFC should lock the architecture that best satisfies those requirements.

A practical workflow:

1. agree on this PRD,
2. trim it into a short decision version if needed,
3. freeze scope for release 1,
4. then adopt the RFC as the technical blueprint.

---

## 18. Product launch definition of done for release 1

Release 1 should be considered complete when a user can:

1. create an optimization job,
2. attach many arms,
3. launch on at least one live surface,
4. measure outcomes and guardrails,
5. use a simple adaptive policy,
6. wake up to a reliable report,
7. inspect why traffic shifted,
8. and promote or pause the job confidently.

