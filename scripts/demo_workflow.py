from __future__ import annotations

import time

import httpx
from caliper_core.models import Job
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient


def build_client(
    *,
    backend: str,
    db_url: str,
    api_url: str,
    api_token: str | None,
) -> EmbeddedCaliperClient | ServiceCaliperClient:
    if backend == "service":
        return ServiceCaliperClient(api_url=api_url, api_token=api_token)
    if backend == "embedded":
        return EmbeddedCaliperClient(db_url=db_url)
    msg = f"Unsupported backend: {backend!r}"
    raise ValueError(msg)


def extract_job_id(created: Job) -> str:
    return created.job_id


def wait_for_server(
    *,
    base_url: str,
    timeout_seconds: float = 20.0,
    server_name: str = "Server",
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=1.5)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    msg = f"{server_name} did not become healthy within {timeout_seconds:.1f}s"
    raise RuntimeError(msg)
