# Caliper OpenClaw Execution Pack

This pack turns the Caliper PRD and RFC into an **execution-ready build kit** for OpenClaw.

Use it when the goal is not just to discuss Caliper, but to let an autonomous agent **create a new repo, build the product from zero, and stop only when the frozen v1 acceptance gates are met**.

## What this pack is for

Caliper is the adaptive decision and measurement layer for autonomous work. It should be able to:

- register many candidate ways of acting,
- assign traffic or work across them,
- measure outcomes, cost, latency, and risk,
- adapt allocation over time,
- and emit trustworthy reports.

This pack is deliberately **not AI-evals-first**. It is written to support:

- website variants,
- email variants,
- prompts and workflows,
- tool sequences,
- agent clusters and organizational topologies later.

## What is frozen here

The reference PRD and RFC are broad. This execution pack freezes the decisions needed to actually ship a usable v1 in a new repo:

- local-first and lightweight,
- embeddable on the same box as OpenClaw,
- also deployable as a small shared service,
- no UI on the critical path,
- simple bandits owned in-house,
- contextual-ready before contextual runtime,
- strong abstractions from day one so later upgrades to Kafka, ClickHouse, Temporal, VW, and richer databases do not require rewriting the product surface.

## Read in this order

1. `OPENCLAW_BOOT_PROMPT.md`
2. `BUILD_CHARTER.md`
3. `IMPLEMENTATION_ROADMAP.md`
4. `REPO_BOOTSTRAP_SPEC.md`
5. `ARCHITECTURE_SPEC.md`
6. `API_AND_EVENT_CONTRACTS.md`
7. `POLICY_AND_OPTIMIZATION_SPEC.md`
8. `ADAPTERS_AND_SURFACES_SPEC.md`
9. `TESTING_AND_ACCEPTANCE_SPEC.md`
10. `EXECUTION_BACKLOG.md`
11. `AGENT_OPERATING_MANUAL.md`
12. `RUNBOOK_AND_DEPLOYMENT_MODES.md`
13. `REFERENCE_PRD.md`
14. `REFERENCE_RFC.md`

## Precedence order

If two docs conflict, use this order:

1. `BUILD_CHARTER.md`
2. `ARCHITECTURE_SPEC.md`
3. `API_AND_EVENT_CONTRACTS.md`
4. `POLICY_AND_OPTIMIZATION_SPEC.md`
5. `ADAPTERS_AND_SURFACES_SPEC.md`
6. `IMPLEMENTATION_ROADMAP.md`
7. `EXECUTION_BACKLOG.md`
8. `AGENT_OPERATING_MANUAL.md`
9. `REFERENCE_PRD.md`
10. `REFERENCE_RFC.md`

Process questions are governed by `AGENT_OPERATING_MANUAL.md`.

## What OpenClaw should deliver

A successful v1 build must let a user or agent:

- create an optimization job,
- attach many arms,
- choose a simple adaptive policy,
- serve or route at least one live surface,
- ingest exposures and outcomes,
- enforce guardrails,
- emit machine-readable and human-readable reports,
- explain traffic shifts,
- and promote, pause, or rollback safely.

## Why there is no UI requirement in v1

A UI is optional. It is not on the critical path. The must-have operator interfaces for v1 are:

- API,
- CLI,
- Python SDK,
- TypeScript SDK,
- JSON reports,
- Markdown or HTML reports.

A minimal console can be added later without blocking the core platform.

## File index

| File | Purpose |
|---|---|
| `OPENCLAW_BOOT_PROMPT.md` | Direct instructions to OpenClaw |
| `BUILD_CHARTER.md` | Frozen scope and architectural decisions |
| `IMPLEMENTATION_ROADMAP.md` | Phase plan and release gates |
| `REPO_BOOTSTRAP_SPEC.md` | Repo layout, toolchain, commands, profiles |
| `ARCHITECTURE_SPEC.md` | Runtime topology and component boundaries |
| `API_AND_EVENT_CONTRACTS.md` | HTTP contracts, event envelopes, schemas |
| `POLICY_AND_OPTIMIZATION_SPEC.md` | Bandits, objectives, guardrails, contextual path |
| `ADAPTERS_AND_SURFACES_SPEC.md` | Web, email, workflow, and org-router adapter rules |
| `TESTING_AND_ACCEPTANCE_SPEC.md` | Tests, demos, release gates |
| `EXECUTION_BACKLOG.md` | Ordered task list with deliverables and acceptance |
| `AGENT_OPERATING_MANUAL.md` | How OpenClaw should work autonomously |
| `RUNBOOK_AND_DEPLOYMENT_MODES.md` | Local, embedded, and shared-service operation |
| `REFERENCE_PRD.md` | Source product document |
| `REFERENCE_RFC.md` | Source engineering document |

## Recommended use

Copy this whole directory into the target repo under `docs/execution/`, then instruct OpenClaw to start with `OPENCLAW_BOOT_PROMPT.md`.
