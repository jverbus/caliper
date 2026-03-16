# Caliper report: Workflow demo (service)

## Summary
- Job ID: `job_203d78261dd1`
- Workspace: `ws-workflow-demo`
- Total assignments: 10
- Total exposures: 10
- Total outcome events: 40

## Leaders
| Arm | Avg reward | Assignment share | Assignments |
| --- | ---: | ---: | ---: |
| `arm-accurate` | 0.2775 | 70.00% | 7 |
| `arm-fast` | 0.2200 | 30.00% | 3 |

## Traffic shifts
- arm-accurate: -1 assignments in later window
- arm-fast: +1 assignments in later window

## Guardrails
- No guardrail events.

## Segment findings
- all (10 observations)

## Recommendations
- **Promote current leader:** Promote arm 'arm-accurate' cautiously (low confidence): avg reward 0.2775 at 70.0% traffic share.
