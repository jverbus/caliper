from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout_seconds: float = 20.0) -> None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("Timed out waiting for API health endpoint")


def test_ts_sdk_can_call_live_api(tmp_path: Path) -> None:
    subprocess.run(
        ["pnpm", "--filter", "@caliper/ts-sdk", "build"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
    )

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    db_path = tmp_path / "caliper-ts-sdk.db"

    env = os.environ.copy()
    env["CALIPER_PROFILE"] = "embedded"
    env["CALIPER_DB_URL"] = f"sqlite:///{db_path.as_posix()}"

    api_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_health(base_url)

        script = """
        import { CaliperClient } from './packages/ts-sdk/dist/index.js';

        const client = new CaliperClient({ baseUrl: process.env.CALIPER_BASE_URL });
        const workspaceId = 'ws-ts-sdk';

        const create = await client.createJob({
          workspace_id: workspaceId,
          name: 'TS SDK integration',
          surface_type: 'web',
          objective_spec: {
            reward_formula: '1.0 * signup',
            penalties: ['0.05 * token_cost_usd'],
            secondary_metrics: ['ctr'],
          },
          guardrail_spec: {
            rules: [{ metric: 'error_rate', op: '<', threshold: 0.02, action: 'pause' }],
          },
          policy_spec: {
            policy_family: 'fixed_split',
            params: { weights: [0.5, 0.5] },
            update_cadence: { mode: 'periodic', seconds: 300 },
            context_schema_version: null,
          },
          segment_spec: { dimensions: ['country'] },
          schedule_spec: { report_cron: '0 7 * * *' },
        });

        const jobId = create.job_id;
        await client.updateJob(jobId, { name: 'TS SDK integration v2' });

        await client.addArms(jobId, {
          workspace_id: workspaceId,
          arms: [
            {
              arm_id: 'arm-a',
              name: 'A',
              arm_type: 'workflow',
              payload_ref: 'prompt://a',
              metadata: {},
            },
            {
              arm_id: 'arm-b',
              name: 'B',
              arm_type: 'workflow',
              payload_ref: 'prompt://b',
              metadata: {},
            },
          ],
        });

        const decision = await client.assign({
          workspace_id: workspaceId,
          job_id: jobId,
          unit_id: 'user-1',
          idempotency_key: 'req-1',
          context: { country: 'US' },
          candidate_arms: null,
        });

        await client.logExposure({
          workspace_id: workspaceId,
          job_id: jobId,
          decision_id: decision.decision_id,
          unit_id: 'user-1',
          exposure_type: 'rendered',
          timestamp: new Date().toISOString(),
          metadata: {},
        });

        await client.logOutcome({
          workspace_id: workspaceId,
          job_id: jobId,
          decision_id: decision.decision_id,
          unit_id: 'user-1',
          events: [
            { outcome_type: 'signup', value: 1.0, timestamp: new Date().toISOString() },
          ],
          attribution_window: { hours: 24 },
          metadata: {},
        });

        await client.generateReport(jobId, { workspace_id: workspaceId });
        const latest = await client.latestReport(jobId, workspaceId);

        process.stdout.write(JSON.stringify({ jobId, reportId: latest.report_id }));
        """

        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "CALIPER_BASE_URL": base_url},
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)
        assert result["jobId"].startswith("job_")
        assert result["reportId"].startswith("rpt_")
    finally:
        api_proc.terminate()
        api_proc.wait(timeout=10)
