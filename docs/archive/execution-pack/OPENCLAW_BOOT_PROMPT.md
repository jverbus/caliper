# OpenClaw Boot Prompt

You are building **Caliper** from zero in a new repository.

Your job is to execute the markdown specs in this directory and produce a working v1 implementation of Caliper: an adaptive decision and measurement layer for autonomous work.

## Mission

Build a local-first, lightweight, modular platform that can be embedded on the same machine as OpenClaw or run as a small shared service. It must support:

- optimization jobs,
- arms or variants,
- simple adaptive policies,
- assignment with propensities,
- exposure and outcome ingestion,
- reward and guardrail evaluation,
- machine-readable and human-readable reports,
- safe pause, promote, rollback, and audit behavior.

It must be broad enough to optimize:

- websites,
- email variants,
- workflows and prompts,
- and later organizational routing.

Do **not** narrow the product to AI evals.

## Read order

Read and obey these files in order:

1. `BUILD_CHARTER.md`
2. `IMPLEMENTATION_ROADMAP.md`
3. `REPO_BOOTSTRAP_SPEC.md`
4. `ARCHITECTURE_SPEC.md`
5. `API_AND_EVENT_CONTRACTS.md`
6. `POLICY_AND_OPTIMIZATION_SPEC.md`
7. `ADAPTERS_AND_SURFACES_SPEC.md`
8. `TESTING_AND_ACCEPTANCE_SPEC.md`
9. `EXECUTION_BACKLOG.md`
10. `AGENT_OPERATING_MANUAL.md`
11. `RUNBOOK_AND_DEPLOYMENT_MODES.md`
12. `REFERENCE_PRD.md`
13. `REFERENCE_RFC.md`

If there is a conflict, the build charter wins.

## Non-negotiable constraints

1. **Local-first**
   - Default to an embedded or same-box deployment.
   - Also support a shared service mode with the same core abstractions.

2. **Lightweight v1**
   - Do not make Kafka, ClickHouse, Redis, Temporal, or a browser UI mandatory in v1.
   - Build the seams so those can be added later.

3. **No UI on the critical path**
   - API, CLI, SDKs, and reports are sufficient for v1.

4. **Own the platform and simple policies**
   - Implement fixed split, epsilon-greedy, UCB1, and Thompson sampling in-house.
   - Do not make external bandit libraries the runtime surface.

5. **Contextual-ready before contextual**
   - Log the right metadata and create the right interfaces before adding contextual policies.
   - Do not implement contextual bandit runtime behavior until the explicit contextual-ready gate is complete.

6. **Strong modularity**
   - Storage, eventing, scheduling, and policy backends must be behind interfaces from the start.
   - Start simple, but do not hardcode the stack.

7. **Broad surface model**
   - Treat websites, emails, workflows, and future organizations as first-class concepts in the domain model.

## First actions

1. Create the repo scaffold described in `REPO_BOOTSTRAP_SPEC.md`.
2. Import this execution pack into `docs/execution/`.
3. Create `docs/adr/`.
4. Create a root `Makefile` or equivalent task runner with the required commands.
5. Implement the configuration system and deployment profiles.
6. Start Phase 0 and Phase 1 tasks from `EXECUTION_BACKLOG.md`.
7. Work strictly in dependency order.
8. Do not begin a later phase until the current phase exit gate passes.

## Execution loop

For each task:

1. Read the task in `EXECUTION_BACKLOG.md`.
2. Implement the smallest correct solution that satisfies the task.
3. Add or update tests.
4. Run all required commands from `TESTING_AND_ACCEPTANCE_SPEC.md`.
5. Update docs if behavior or architecture changed.
6. If a decision changes scope or architecture, create an ADR before proceeding.
7. Mark the task complete only after acceptance criteria pass.

## Required output discipline

After each completed task or PR-sized unit, write:

- what changed,
- why it changed,
- tests run,
- commands used,
- files created,
- any follow-up tasks.

## Things you must not do

- Do not invent new product scope beyond the frozen charter.
- Do not build a dashboard before the core loop works.
- Do not implement generalized hierarchical routing in v1.
- Do not add contextual bandits before contextual-ready infrastructure is complete.
- Do not introduce heavy infrastructure without an ADR and evidence that a current phase requires it.
- Do not collapse interfaces just because the first implementation is simple.

## Stop condition

Stop only when the v1 release gate in `TESTING_AND_ACCEPTANCE_SPEC.md` passes and the repo contains:

- working embedded mode,
- working shared-service mode,
- workflow adapter,
- web adapter,
- email adapter,
- CLI,
- Python SDK,
- TypeScript SDK,
- reports,
- and a runbook showing how to operate the system.

At that point, update the roadmap and backlog with remaining post-v1 work and create a final delivery summary.
