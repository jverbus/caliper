#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Defaults are safe for demo dry-run mode; override by passing your own args.
DEFAULT_ARGS=(
  --topic "Caliper email demo"
  --recipients "demo1@example.com,demo2@example.com,demo3@example.com,demo4@example.com"
  --variant-count 5
  --mode dry_run
  --backend embedded
  --open-tunnel
)

echo "[caliper] Launching email demo with Cloudflare quick tunnel..."
echo "[caliper] Demo-only warning: tracked links become publicly reachable while the run is active."
echo "[caliper] For real sends, pass --mode live and valid Gmail SMTP env vars."

"${REPO_ROOT}/run_email_demo" "${DEFAULT_ARGS[@]}" "$@"
