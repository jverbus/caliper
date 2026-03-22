# Policy and Optimization Spec

This document defines how Caliper should handle policies, reward logic, guardrails, bandits, and the path to contextual methods.

## 1. Product stance

Caliper is not a generic bandit library. It is the operating layer that decides how real work is allocated and how success is measured.

Therefore, the policy subsystem must fit the product rather than dictate it.

## 2. Build vs buy

### 2.1 Build in-house in v1

Implement these yourself:

- fixed split
- epsilon-greedy
- UCB1
- Thompson sampling for Bernoulli rewards
- Thompson-style numeric reward variant if needed
- policy snapshotting
- policy update lifecycle
- reward formulas
- guardrails
- diagnostics and explainability

Why:

- simple enough to own,
- easier to test,
- easier to explain,
- avoids making an external library the product surface.

### 2.2 Use external libraries later, behind interfaces

Future or optional integrations:

- Vowpal Wabbit for richer contextual bandits and action-dependent features
- OBP for replay and off-policy evaluation workflows
- MABWiser for validation or simulations only
- `contextualbandits` only as a sandbox if useful

These must sit behind Caliper-owned interfaces.

## 3. Policy interface

Every policy backend must satisfy a stable interface.

Suggested contract:

```python
class Policy(Protocol):
    def choose(self, request: DecisionRequest) -> DecisionResult: ...
    def update(self, batch: list[OutcomeRecord]) -> UpdateResult: ...
    def snapshot(self) -> PolicySnapshot: ...
    def validate(self) -> list[ValidationIssue]: ...
```

Required properties:

- returns chosen arm and propensity,
- uses immutable versioned snapshots,
- can be replayed deterministically,
- emits diagnostics,
- handles cold start,
- handles arm addition and retirement,
- supports fallback behavior.

## 4. Built-in policy families for v1

### 4.1 Fixed split

Use for classic A/B/n and safe launch baselines.

### 4.2 Epsilon-greedy

Use when a simple and explainable exploration strategy is sufficient.

### 4.3 UCB1

Use when uncertainty-based exploration is wanted with easy interpretation.

### 4.4 Thompson sampling

Use as the likely default adaptive policy for many binary-outcome jobs.

V1 should at least support:

- Bernoulli reward form
- a documented numeric-reward extension path

## 5. Update strategy

V1 should favor **micro-batch snapshot updates**, not in-request mutation.

Why:

- easier to debug,
- easier to reproduce,
- easier to rollback,
- easier to explain,
- safer for delayed outcomes.

Recommended defaults:

- workflow and web jobs: frequent periodic updates, for example every 1 to 5 minutes in demos
- email jobs: tranche-boundary updates
- configurable cadence per policy spec

The assignment path must always use an immutable current snapshot.

## 6. Objective model

Caliper must not hardcode one metric like CTR.

Each job defines:

- primary reward formula,
- optional secondary metrics,
- penalties,
- hard guardrails.

Example:

```yaml
objective:
  reward_formula: "1.0 * signup + 0.2 * qualified_demo"
  penalties:
    - "0.05 * token_cost_usd"
    - "0.02 * p95_latency_seconds"
```

## 7. Guardrail model

Guardrails are independent from reward.

Examples:

- unsubscribe rate below threshold
- complaint rate below threshold
- error rate below threshold
- latency below threshold
- cost per decision below threshold

Supported actions:

- annotate report,
- cap traffic,
- demote arm,
- pause job,
- require manual approval before resume.

## 8. Decision diagnostics

Every decision should expose enough data to explain itself.

V1 minimum:

- chosen arm,
- eligible arms,
- policy family,
- policy version,
- propensity,
- decision reason,
- scores or samples where meaningful,
- fallback indicator if used.

Diagnostics may be partially redacted externally if needed, but they must exist internally.

## 9. Segment-aware analysis without contextual runtime

V1 must support segment-aware reporting even before contextual policies.

How:

- store configured segment dimensions,
- log decision metadata and context fields safely,
- aggregate outcomes by segment in reports,
- do not let segment-specific policy logic drive routing yet unless explicitly implemented.

## 10. Cold start and arm changes

Policies must specify behavior for:

- new jobs with no outcomes,
- new arms entering an active job,
- retired arms,
- held-out arms,
- minimum traffic floors.

Initial recommendations:

- fixed minimum exploration floor for active eligible arms,
- warm-start rules configurable but conservative,
- arm retirement must remove the arm from future assignment but preserve history.

## 11. Fallback policies

If the target policy cannot score or is unavailable, Caliper must use a safe fallback.

Allowed fallbacks:

- fixed split,
- random among eligible arms,
- last known good snapshot.

The response must indicate that fallback was used.

## 12. Simulation and sanity tests

Before a policy is accepted into runtime, it must pass:

- deterministic unit tests,
- probability normalization tests,
- cold-start tests,
- arm retirement tests,
- simulation sanity tests,
- replay consistency tests if applicable.

## 13. Contextual-ready contract

V1 must lay the substrate for future contextual policies.

Required additions before contextual runtime:

- `context_schema_version`
- versioned context validation
- candidate arms per request
- logged propensities
- replay export format
- shadow policy state
- feature parity test scaffolding

## 14. First contextual policy after v1

The first in-house contextual policy should be **disjoint LinUCB**.

Reasons:

- understandable,
- inspectable,
- good for fixed or small arm sets,
- lower implementation risk than jumping directly to more complex contextual backends.

## 15. Vowpal Wabbit stance

VW should not appear in the critical path for v1.

After v1, add it behind a `PolicyBackend` adapter for:

- variable action sets,
- action-dependent features,
- more advanced exploration strategies,
- larger-scale contextual experimentation.

The rest of the codebase must not leak VW CLI flags or data formats.

## 16. OPE stance

Offline policy evaluation is required before contextual policies become live, but it does not need to block the non-contextual v1 build.

V1 should ship with:

- replay export schema,
- OPE package scaffold,
- no live contextual auto-promotion.

## 17. Numeric reward and multiple signals

The reward engine should convert raw outcomes into a policy-ready reward.

Suggested pipeline:

1. join decision, exposure, outcome, and cost events
2. compute attribution-window-safe aggregates
3. apply reward formula
4. apply penalties
5. write policy-update records and report aggregates

Policy implementations do not need to know every raw metric directly if the reward engine can produce the normalized update dataset they need.

## 18. Why this spec is frozen

The key risk is building a narrow algorithm playground instead of a usable operating product.

This policy spec prevents that by making:

- objectives configurable,
- guardrails explicit,
- decisions auditable,
- and later contextual power optional rather than destabilizing.
