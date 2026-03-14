from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from caliper_core.models import PolicySpec


@dataclass(frozen=True)
class ContextValidationResult:
    sanitized_context: dict[str, Any]


class ContextValidationError(ValueError):
    """Raised when an assignment context payload violates policy schema rules."""


def validate_and_redact_context(
    *,
    context: dict[str, Any],
    policy_spec: PolicySpec,
) -> ContextValidationResult:
    """Validate context against the active schema version and apply redaction hooks."""

    schema_version = policy_spec.context_schema_version
    if schema_version is None:
        return ContextValidationResult(sanitized_context=context)

    schema_registry = policy_spec.params.get("context_schemas")
    if not isinstance(schema_registry, dict):
        msg = (
            "Policy requires context_schema_version but policy params do not define "
            "a context_schemas registry."
        )
        raise ContextValidationError(msg)

    schema_config = schema_registry.get(schema_version)
    if not isinstance(schema_config, dict):
        msg = f"No context schema config found for version '{schema_version}'."
        raise ContextValidationError(msg)

    required_fields = _string_set(schema_config.get("required_fields"))
    allowed_fields = _string_set(schema_config.get("allowed_fields"))
    redact_fields = _string_set(schema_config.get("redact_fields"))

    missing = sorted(field for field in required_fields if field not in context)
    if missing:
        msg = (
            f"Context is missing required field(s) for schema '{schema_version}': "
            f"{', '.join(missing)}"
        )
        raise ContextValidationError(msg)

    if allowed_fields:
        disallowed = sorted(key for key in context if key not in allowed_fields)
        if disallowed:
            msg = (
                f"Context includes disallowed field(s) for schema '{schema_version}': "
                f"{', '.join(disallowed)}"
            )
            raise ContextValidationError(msg)

    sanitized = dict(context)
    for field in redact_fields:
        if field in sanitized:
            sanitized[field] = "[REDACTED]"

    return ContextValidationResult(sanitized_context=sanitized)


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}
