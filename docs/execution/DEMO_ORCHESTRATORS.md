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
- In `live` mode, starts a local HTTP server and fetches served variant pages during traffic simulation
- Generates report artifacts and `winner_summary.json`

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
- Includes Gmail provider scaffold (`GmailProvider`) activated in `live` mode when env is configured:
  - `GMAIL_SMTP_USER`
  - `GMAIL_SMTP_APP_PASSWORD`
  - optional `GMAIL_SMTP_FROM`
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
