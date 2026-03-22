# Agent Operating Manual

This manual tells OpenClaw how to execute the Caliper build autonomously.

## 1. Operating principle

You are not here to brainstorm endlessly. You are here to ship the frozen build charter with disciplined iteration.

Work like a careful staff engineer:

- read the spec,
- make the smallest complete change,
- add tests,
- document the result,
- move to the next ready task.

## 2. Decision precedence

For implementation questions:

1. `BUILD_CHARTER.md`
2. `ARCHITECTURE_SPEC.md`
3. `API_AND_EVENT_CONTRACTS.md`
4. `POLICY_AND_OPTIMIZATION_SPEC.md`
5. `ADAPTERS_AND_SURFACES_SPEC.md`
6. `IMPLEMENTATION_ROADMAP.md`
7. `EXECUTION_BACKLOG.md`
8. reference docs

For process questions:

1. this manual
2. the backlog
3. the roadmap

## 3. Work loop

For each task:

1. confirm dependencies are complete,
2. read the task carefully,
3. implement only what the task requires,
4. add or update tests,
5. run the required commands,
6. update docs if behavior changed,
7. create an ADR if architecture or scope changed,
8. write a short completion note,
9. mark the task complete.

## 4. Required behavior after each task

Record:

- task ID,
- summary of change,
- files added or changed,
- tests run,
- commands run,
- known follow-ups.

Keep this note in a work log or PR description.

## 5. When an ADR is mandatory

Create an ADR before proceeding if you need to:

- introduce a major dependency not already frozen,
- change storage strategy,
- change eventing strategy,
- change scheduler strategy,
- change a public API contract,
- alter the frozen v1 scope,
- add a mandatory service not in the build charter,
- remove a required interface seam.

## 6. When you may proceed without an ADR

You may proceed directly for:

- internal refactors that preserve behavior,
- small library substitutions inside a frozen tool class,
- doc clarifications,
- tests,
- demos,
- minor implementation details that do not alter the public contract.

## 7. Coding rules

- prefer explicit, typed code,
- keep modules small,
- separate interfaces from implementations,
- avoid circular dependencies,
- do not duplicate schema definitions across languages,
- favor deterministic behavior in tests,
- keep logging structured.

## 8. Product guardrails

Never let the code drift into any of these traps:

- “Caliper is basically a dashboard”
- “Caliper is basically an eval harness”
- “Caliper is basically a single-surface web test tool”
- “Caliper is basically a bandit library with no operational layer”

The whole point is a broad adaptive operating layer.

## 9. Scope guardrails

Do not do these before the release-1 gate passes:

- heavy infra adoption,
- UI-first work,
- generalized hierarchical routing,
- contextual runtime policies,
- large research-only subsystems.

## 10. Test discipline

Before marking a task done:

- run the task-specific tests,
- run any impacted integration tests,
- keep the repo green.

Before major phase completion:

- run the relevant demo,
- update sample outputs if needed,
- verify docs still match.

## 11. Documentation discipline

Update docs whenever:

- a contract changes,
- a command changes,
- a file path changes,
- a runtime mode changes,
- a demo flow changes.

Do not leave the docs for later if the code changes the operating surface.

## 12. Handling ambiguity

If the spec leaves room for choice:

- choose the simplest implementation that preserves the interface,
- prefer local-first and low-ops,
- prefer the smaller dependency set,
- prefer the more explainable behavior,
- document the choice briefly.

If the choice changes scope or architecture, write an ADR.

## 13. Handling blockers

If blocked:

1. check whether the blocker is actually a missing dependency task,
2. complete the missing dependency,
3. if still blocked, create a small ADR or decision note,
4. choose the minimal compliant path forward.

Do not halt the whole build for optional future-facing questions.

## 14. Delivery unit size

Target PR-sized changes, not giant dumps.

Good delivery unit:

- one task or a tightly coupled pair of tasks,
- code plus tests plus docs.

Bad delivery unit:

- a whole phase without intermediate verification.

## 15. Definition of task done

A task is done only when:

- deliverables exist,
- acceptance criteria pass,
- tests are present,
- commands were run,
- docs are updated,
- the work log is written.

## 16. Completion note template

```md
## Task Complete: P3-002

### Summary
Implemented `/v1/assign` with DB-backed idempotency and fixed-split selection.

### Files
- apps/api/...
- packages/py-caliper-policies/...
- tests/integration/...

### Tests
- make test-integration
- make test-unit

### Notes
- Retries now return original decision when the same idempotency key is reused.
- Follow-up: wire adaptive policies in Phase 4.
```

## 17. ADR template

```md
# ADR-00X: Title

## Status
Proposed | Accepted | Superseded

## Context
What problem or tension exists?

## Decision
What is being chosen?

## Alternatives considered
- Option A
- Option B

## Consequences
What gets simpler, harder, better, or riskier?

## Why this fits the build charter
Explain alignment with local-first, lightweight, and modular goals.
```

## 18. PR summary template

```md
## Summary
What changed?

## Why
Which task or acceptance criteria does it satisfy?

## Scope
What is included and what is intentionally not included?

## Tests
Which commands were run?

## Docs
Which docs were updated?

## Follow-ups
What remains for later tasks?
```

## 19. Final delivery rule

When the release-1 gate passes, write a final delivery summary that includes:

- features implemented,
- demos that pass,
- deployment modes that work,
- known post-v1 items,
- and references to runbooks and reports.
