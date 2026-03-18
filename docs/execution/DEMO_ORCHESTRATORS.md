# Demo orchestrators (landing + email)

This adds top-level one-command demo runners requested for implementation handoff.

## Landing page demo

Command:

```bash
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode dry_run
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_only --backend embedded --observe-seconds 180
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_and_simulate --backend embedded
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode live
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_only --open-tunnel
./run_landing_page_demo --topic "Caliper LP demo" --variant-count 5 --mode serve_and_simulate --public-base-url https://demo.example.com
scripts/run_landing_demo_with_tunnel.sh
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
  - `POST /lp/{job_id}/events` browser tracker telemetry ingest
  - `GET /lp/{job_id}/report` latest report payload
- Mode behavior:
  - `dry_run`: in-process synthetic simulation
  - `serve_only`: real server, no synthetic driver (manual/external traffic window)
  - `serve_and_simulate`: real server + synthetic visitor driver against live routes
  - `live`: alias for `serve_and_simulate`
- Supports backend selection:
  - `--backend embedded` → `EmbeddedCaliperClient`
  - `--backend service` → `ServiceCaliperClient --api-url ...`
- Public URL support for served modes:
  - `--public-base-url https://...` rewrites canonical demo/report URLs in output manifests.
  - `--open-tunnel` starts a Cloudflare quick tunnel after local `/healthz` succeeds.
- Served modes bootstrap browser tracker helpers (`apps/demo_web/static/browser_tracker.js`) with:
  - retry/backoff queue + localStorage persistence,
  - beacon/keepalive delivery fallback,
  - delegated click helper (`click_detail`),
  - auto visible-time helper (`time_spent`).
- Served modes also bootstrap an operator panel (`apps/demo_web/static/operator_panel.js`) with:
  - current visitor/decision/arm context,
  - explicit **Reset identity** and **Force new visitor** controls,
  - backend/telemetry mode and `/healthz` tracking endpoint status.
- Tracker toggles can be passed as query params on landing routes: `browser_tracker=0`, `track_time_spent=0`, `track_clicks=0`.
- Operator actions route through query params: `force_new_visitor=1` and `operator_action=<action_name>`.
- Outcome metadata source markers:
  - `source=browser_tracker` for `/lp/{job_id}/events` ingestion,
  - `source=landing_demo_server` (real routes) / `source=landing_demo_inprocess` (dry-run simulator) for server-origin events,
  - `force_new_visitor` + `operator_action` fields on landing render exposures.
- Generates report artifacts and canonical `winner_summary.json` (backend/mode/provider, URLs, traffic source, browser telemetry, operator controls, and metrics)

Output:

- `reports/landing_page_demo/<mode>/report.{json,md,html}`
- `reports/landing_page_demo/<mode>/winner_summary.json`
- `reports/landing_page_demo/<mode>/variants/*.html`
- `reports/landing_page_demo/<mode>/server_config.json` (for served modes)
- `reports/landing_page_demo/<mode>/server.log` (for served modes)
- `reports/landing_page_demo/<mode>/cloudflared_tunnel.log` (when `--open-tunnel` is used)
- `winner_summary.json` includes `browser_tracker` section for served telemetry manifests

## Email demo

Command:

```bash
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --backend embedded
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --backend service --api-url http://127.0.0.1:8000
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode live --backend embedded
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode dry_run --open-tunnel
./run_email_demo --topic "Caliper email demo" --recipients "a@example.com,b@example.com" --variant-count 5 --mode live --public-base-url https://demo.example.com
scripts/run_email_demo_with_tunnel.sh
```

Behavior:

- Generates `variant_count` email subject variants and registers as arms
- Supports both backends:
  - `--backend embedded` → `EmbeddedCaliperClient`
  - `--backend service` → `ServiceCaliperClient --api-url ...`
- Uses tranche planning + provider seam (`DryRunProvider`)
- Includes Gmail provider scaffold (`GmailProvider`) for real sends in `live` mode:
  - required: `GMAIL_SMTP_USER`
  - required: `GMAIL_SMTP_APP_PASSWORD`
  - optional: `GMAIL_SMTP_FROM`
- In `live` mode, missing Gmail credentials fail fast (no silent fallback to dry-run provider)
- Starts `apps.demo_email` tracking server and wires message links to tracked endpoints:
  - `GET /email/{job_id}/click` (tracked click)
  - `GET|POST /email/{job_id}/convert` (tracked conversion)
  - `GET|POST /email/{job_id}/reply` (reply-signal ingest)
- `dry_run` uses a synthetic tracked-route driver so click/conversion/reply signals flow through those routes
- `live` defaults to real-send-only behavior (no synthetic tracked-route driver); use `--simulate-tracked-events` to opt in
- Public URL support:
  - `--public-base-url https://...` rewrites canonical tracked/report URLs in output manifests.
  - `--open-tunnel` starts a Cloudflare quick tunnel after local `/healthz` succeeds.
- Open/unsubscribe demo signals remain synthetic webhook events when synthetic driving is enabled
- Embedded backend runs inline policy-update worker ticks between tranches; service backend expects an external worker
- Generates report artifacts plus a canonical `winner_summary.json` manifest containing backend/mode/provider, tracked URLs, measurement mode, metrics, and artifact paths
- Writes `dispatch_manifest.json` with per-recipient decision IDs and tracked URLs for replay/audit
- Reply signal first-step ingest command is available via `scripts/ingest_email_reply_signal.py`

Output:

- `reports/email_demo/<mode>/report.{json,md,html}`
- `reports/email_demo/<mode>/winner_summary.json`
- `reports/email_demo/<mode>/dispatch_manifest.json`
- `reports/email_demo/<mode>/tracking_server_config.json`
- `reports/email_demo/<mode>/tracking_server.log`
- `reports/email_demo/<mode>/cloudflared_tunnel.log` (when `--open-tunnel` is used)

## Public tunnel workflow (demo-only)

Use this when you need externally reachable links for customer/investor/operator walkthroughs.

1. Start local demo server + tunnel in one command:
   - Landing: `scripts/run_landing_demo_with_tunnel.sh`
   - Email: `scripts/run_email_demo_with_tunnel.sh`
2. Share URLs from CLI JSON output (`public_urls`) or from `winner_summary.json`.
3. Keep the shell session open while the walkthrough is active.
4. Stop with `Ctrl-C` (or let the run complete); Caliper tears down local server and tunnel process.

Security caveats:

- Treat quick tunnels as temporary public exposure of your local demo endpoint.
- Use demo-only data and avoid exposing real user payloads.
- Prefer short `--observe-seconds` windows and close sessions immediately after demos.
- Review `cloudflared_tunnel.log` for troubleshooting and URL confirmation.

## Live walkthrough script (customer/investor/operator)

1. Run landing demo in served mode (`serve_only` for fully real traffic, `serve_and_simulate`/`live` for assisted flow).
2. Share `demo_url`; call out Operator Panel fields (visitor, decision, arm, backend mode, telemetry mode).
3. Click **Force new visitor** to show fresh assignment path (URL carries `force_new_visitor=1&operator_action=force_new_visitor`).
4. Click **Reset identity** to clear cookie context and run a brand-new assignment (`operator_action=reset_identity`).
5. Optionally compare with `browser_tracker=0` to explain browser telemetry on/off behavior.
6. Open `report_url` + `winner_summary.json` to connect observed behavior to measured outcomes and operator-control metadata.

## Validation

- `make lint`
- `make typecheck`
- `make test`
- `./run_landing_page_demo ... --mode dry_run`
- `./run_landing_page_demo ... --mode serve_and_simulate --backend embedded`
- `./run_email_demo ... --mode dry_run --backend embedded`
- `./run_email_demo ... --mode dry_run --backend service --api-url http://127.0.0.1:8000`
