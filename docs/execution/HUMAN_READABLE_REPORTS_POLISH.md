# P8-001 Human-readable reports polish

## Scope

Improves operator-facing report readability without requiring a UI by tightening:

- stable Markdown structure,
- semantic HTML rendering,
- recommendation language rules.

## What changed

- Added a deterministic **Summary** section with total assignments/exposures/outcome-event counts.
- Standardized **Leaders** output into a fixed Markdown table and matching HTML table.
- Replaced preformatted HTML blob output with explicit semantic sections (`h1/h2`, `ul`, `table`) for easier consumption in docs and exported artifacts.
- Added recommendation wording rules:
  - confidence-aware leader promotion language (`low`/`medium`/`high` confidence tiers by assignment volume),
  - explicit guardrail escalation guidance when events exist,
  - fallback guidance to collect more evidence when no signal exists.

## Acceptance mapping

- Reports are understandable without UI:
  - headline summary numbers,
  - ranked leaders table,
  - clearly labeled sections for traffic shifts, guardrails, segment findings, recommendations.
- Sample outputs remain check-in friendly and deterministic through persisted report payloads.

## Tests

- Unit coverage for polished rendering sections and recommendation language rules:
  - `tests/unit/test_report_generator.py`
- Integration expectation update for report generation response shape:
  - `tests/integration/test_api_reports.py`
