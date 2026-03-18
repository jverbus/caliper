# Demo orchestrators (landing + email)

This adds top-level one-command demo runners requested for implementation handoff.

## Landing page demo

Command:

```bash
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode dry_run
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_only --backend embedded --observe-seconds 180
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_and_simulate --backend embedded
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode live
```

Behavior:

- Generates `variant_count` landing page artifacts (HTML files)
- Registers variants as arms and runs request-time assignment + telemetry
- Starts `apps.demo_web` FastAPI server for non-`dry_run` modes
- Landing route set:
  - `GET /lp/{job_id}` assign + render + exposure
  - `GET /lp/{job_id}/click` click tracking + redirect
  - `GET /lp/{job_id}/offer` intermediate offer page
  - `POST /lp/{job_id}/convert` conversion tracking
  - `GET /lp/{job_id}/report` latest report payload
- Mode behavior:
  - `dry_run`: in-process synthetic simulation
  - `serve_only`: real server, no synthetic driver (manual/external traffic window)
  - `serve_and_simulate`: real server + synthetic visitor driver against live routes
  - `live`: alias for `serve_and_simulate`
- Supports backend selection:
  - `--backend embedded` → `EmbeddedCaliperClient`
  - `--backend service` → `ServiceCaliperClient --api-url ...`
- Generates report artifacts and `winner_summary.json` (including traffic source + URLs)

Output:

- `reports/landing_page_demo/<mode>/report.{json,md,html}`
- `reports/landing_page_demo/<mode>/winner_summary.json`
- `reports/landing_page_demo/<mode>/variants/*.html`
- `reports/landing_page_demo/<mode>/server_config.json` (for served modes)
- `reports/landing_page_demo/<mode>/server.log` (for served modes)

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
- `./run_landing_page_demo ... --mode serve_and_simulate --backend embedded`
- `./run_email_demo ... --mode dry_run`
