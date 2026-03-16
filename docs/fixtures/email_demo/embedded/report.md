# Caliper report: Email demo (embedded)

## Summary
- Job ID: `job_a5b8c3fc5479`
- Workspace: `ws-email-demo`
- Total assignments: 10
- Total exposures: 10
- Total outcome events: 26

## Leaders
| Arm | Avg reward | Assignment share | Assignments |
| --- | ---: | ---: | ---: |
| `subject-a` | 1.0333 | 60.00% | 6 |
| `subject-b` | -1.0000 | 40.00% | 4 |

## Traffic shifts
- subject-a: +4 assignments in later window
- subject-b: -4 assignments in later window

## Guardrails
- `email_unsubscribe` status=`breach` action=`cap`
- `email_unsubscribe` status=`breach` action=`cap`

## Segment findings
- all (10 observations)

## Recommendations
- **Promote current leader:** Promote arm 'subject-a' cautiously (low confidence): avg reward 1.0333 at 60.0% traffic share.
- **Resolve guardrail alerts before scaling:** 2 guardrail event(s) detected. Keep rollout constrained until breached metrics return to expected ranges.
