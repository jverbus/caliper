from __future__ import annotations

import hashlib
import json

from caliper_core.models import AssignRequest


def request_hash(payload: object) -> str:
    if hasattr(payload, "model_dump"):
        body = payload.model_dump(mode="json")
    else:
        body = payload
    encoded = json.dumps(body, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def assign_request_hash(payload: AssignRequest) -> str:
    return request_hash(payload)
