#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default to a live operator walkthrough window. Override by passing your own args.
DEFAULT_ARGS=(
  --topic "Caliper landing demo"
  --variant-count 5
  --mode serve_only
  --backend embedded
  --observe-seconds 300
  --open-tunnel
)

echo "[caliper] Launching landing demo with Cloudflare quick tunnel..."
echo "[caliper] Demo-only warning: this exposes your local demo endpoint publicly while running."
echo "[caliper] Press Ctrl-C to stop early (server + tunnel shutdown are handled automatically)."

"${REPO_ROOT}/run_landing_page_demo" "${DEFAULT_ARGS[@]}" "$@"
