# Caliper report: Web demo (service)

## Summary
- Job ID: `job_291b93614d30`
- Workspace: `ws-web-demo`
- Total assignments: 12
- Total exposures: 12
- Total outcome events: 11

## Leaders
| Arm | Avg reward | Assignment share | Assignments |
| --- | ---: | ---: | ---: |
| `landing-b` | 0.5625 | 41.67% | 5 |
| `landing-a` | 0.3000 | 58.33% | 7 |

## Traffic shifts
- landing-a: -3 assignments in later window
- landing-b: +3 assignments in later window

## Guardrails
- No guardrail events.

## Segment findings
- country=US (7 observations)
- device=mobile (7 observations)

## Recommendations
- **Promote current leader:** Promote arm 'landing-b' cautiously (low confidence): avg reward 0.5625 at 41.7% traffic share.
