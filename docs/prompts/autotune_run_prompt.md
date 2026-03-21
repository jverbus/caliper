# autotune_run_prompt

Run one deterministic baseline-vs-candidate simulation comparison.

Requirements:

- same `seed` and `budget` for both variants
- same frozen `simulation_config_snapshot`
- evaluator version fixed (`fixed-v1`)

After run completion, summarize:

- candidate score
- baseline score
- delta vs baseline
- keep/discard outcome
- reason and hard-fail code (if present)
