# autotune_promotion_prompt

Before promotion, validate all of the following:

1. candidate/run IDs match.
2. run result exists and disposition is recorded.
3. explicit confirmation token is present:
   - `CONFIRM_AUTOTUNE_PROMOTION`
4. replay check passes.

If any check fails, stop and report failure details.
If all checks pass, submit promotion payload and include a concise diff summary.
