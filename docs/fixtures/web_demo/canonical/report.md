# Caliper report: Web demo (embedded)

## Summary
- Job ID: `job_001c42c10bba`
- Workspace: `ws-web-demo`
- Total assignments: 12
- Total exposures: 12
- Total outcome events: 11

## Leaders
| Arm | Avg reward | Assignment share | Assignments |
| --- | ---: | ---: | ---: |
| `landing-b` | 0.6000 | 33.33% | 4 |
| `landing-a` | 0.3000 | 66.67% | 8 |

## Traffic shifts
- landing-a: +2 assignments in later window
- landing-b: -2 assignments in later window

## Guardrails
- No guardrail events.

## Segment findings
- country=US (7 observations)
- device=mobile (7 observations)

## Recommendations
- **Promote current leader:** Promote arm 'landing-b' cautiously (low confidence): avg reward 0.6000 at 33.3% traffic share.
