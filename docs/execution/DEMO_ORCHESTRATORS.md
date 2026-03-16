# Demo orchestrators (landing + email)

This adds top-level one-command demo runners requested for implementation handoff.

## Landing page demo

Command:

```bash
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode dry_run
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode live
```

Behavior:

- Generates `variant_count` landing page artifacts (HTML files)
- Registers variants as arms and runs request-time assignment + telemetry
- `dry_run` mode uses in-process synthetic simulation
- `live` mode currently starts a local HTTP server and runs synthetic closed-loop traffic against served pages (external-visitor traffic mode follows in the next delta chunk)
- Generates report artifacts and `winner_summary.json` (including `traffic_source`)

Output:

- `reports/landing_page_demo/<mode>/report.{json,md,html}`
- `reports/landing_page_demo/<mode>/winner_summary.json`
- `reports/landing_page_demo/<mode>/variants/*.html`

## Email demo

Command:

```bash
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode live
```

Behavior:

- Generates `variant_count` email subject variants and registers as arms
- Uses tranche planning + provider seam (`DryRunProvider`)
- Includes Gmail provider scaffold (`GmailProvider`) for real sends in `live` mode:
  - required: `GMAIL_SMTP_USER`
  - required: `GMAIL_SMTP_APP_PASSWORD`
  - optional: `GMAIL_SMTP_FROM`
- In `live` mode, missing Gmail credentials now fail fast (no silent fallback to dry-run provider)
- Logs delayed open/click/conversion and unsubscribe outcomes
- Executes policy-update worker tasks between tranches to demonstrate adaptation
- Generates report artifacts and `winner_summary.json`

Output:

- `reports/email_demo/<mode>/report.{json,md,html}`
- `reports/email_demo/<mode>/winner_summary.json`

## Validation

- `make lint`
- `make typecheck`
- `make test`
- `./run_landing_page_demo ... --mode dry_run`
- `./run_email_demo ... --mode dry_run`
