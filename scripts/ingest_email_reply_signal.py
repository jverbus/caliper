from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from caliper_adapters import EmailAdapter, EmailWebhookEvent, EmailWebhookType
from caliper_sdk import EmbeddedCaliperClient, ServiceCaliperClient

type DemoClient = EmbeddedCaliperClient | ServiceCaliperClient


def _build_client(
    *,
    backend: str,
    db_url: str,
    api_url: str,
    api_token: str | None,
) -> DemoClient:
    if backend == "service":
        return ServiceCaliperClient(api_url=api_url, api_token=api_token)
    if backend == "embedded":
        return EmbeddedCaliperClient(db_url=db_url)
    msg = f"Unsupported backend: {backend!r}"
    raise ValueError(msg)


def ingest_reply_signal(
    *,
    backend: str,
    db_url: str,
    api_url: str,
    api_token: str | None,
    workspace_id: str,
    job_id: str,
    recipient_id: str,
    decision_id: str,
    webhook_event_id: str | None,
    value: float,
    metadata: dict[str, str | int | float | bool],
) -> dict[str, Any]:
    client = _build_client(
        backend=backend,
        db_url=db_url,
        api_url=api_url,
        api_token=api_token,
    )
    adapter = EmailAdapter(client=client, workspace_id=workspace_id, job_id=job_id)

    resolved_event_id = webhook_event_id or (
        f"reply-{decision_id}-{int(datetime.now(tz=UTC).timestamp())}"
    )
    outcome = adapter.ingest_webhook(
        event=EmailWebhookEvent(
            webhook_event_id=resolved_event_id,
            webhook_type=EmailWebhookType.REPLY,
            recipient_id=recipient_id,
            decision_id=decision_id,
            occurred_at=datetime.now(tz=UTC),
            value=value,
            metadata={"source": "manual_reply_ingest", **metadata},
        )
    )

    return {
        "status": "duplicate" if outcome is None else "ingested",
        "backend": backend,
        "workspace_id": workspace_id,
        "job_id": job_id,
        "recipient_id": recipient_id,
        "decision_id": decision_id,
        "webhook_event_id": resolved_event_id,
        "metric": "email_reply",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a reply signal for the email demo")
    parser.add_argument("--backend", choices=["embedded", "service"], default="embedded")
    parser.add_argument("--db-url", default="sqlite:///./data/email-orchestrator-demo.db")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--recipient-id", required=True)
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--webhook-event-id", default=None)
    parser.add_argument("--value", type=float, default=1.0)
    parser.add_argument(
        "--metadata-json",
        default="{}",
        help="JSON object merged into webhook metadata",
    )
    args = parser.parse_args()

    raw_metadata = json.loads(args.metadata_json)
    if not isinstance(raw_metadata, dict):
        raise ValueError("--metadata-json must decode to an object")

    metadata: dict[str, str | int | float | bool] = {}
    for key, value in raw_metadata.items():
        if isinstance(value, (str, int, float, bool)):
            metadata[str(key)] = value

    result = ingest_reply_signal(
        backend=args.backend,
        db_url=args.db_url,
        api_url=args.api_url,
        api_token=args.api_token,
        workspace_id=args.workspace_id,
        job_id=args.job_id,
        recipient_id=args.recipient_id,
        decision_id=args.decision_id,
        webhook_event_id=args.webhook_event_id,
        value=args.value,
        metadata=metadata,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
