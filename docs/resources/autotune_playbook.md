# caliper://autotune_playbook

Canonical MCP-first autotune playbook.

1. Define experiment scope and allowlisted editable surface.
2. Register baseline candidate.
3. Register candidate variant.
4. Execute `autotune_run` with frozen seed/budget/simulation config.
5. Read status + result.
6. Apply keep/discard with explicit reason.
7. If promoting, require explicit confirmation token and replay-check pass.
8. Export JSONL record for audit/history.

Guardrails:

- Simulation-only evaluation for v1.
- Human-gated promotion only.
- No automatic rollout actions.
