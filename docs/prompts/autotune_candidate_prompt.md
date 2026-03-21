# autotune_candidate_prompt

Given a baseline artifact and a narrowly-scoped objective, propose one candidate mutation that:

- edits only the allowlisted `editable_surface`
- keeps safety constraints intact
- limits complexity increase
- includes a short rationale for expected lift

Output JSON fields:

- `experiment_id`
- `candidate_type`
- `parent_candidate_id`
- `editable_surface`
- `content`
- `complexity_score`
