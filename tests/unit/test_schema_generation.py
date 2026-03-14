from __future__ import annotations

from caliper_core.schemas import generate_json_schemas


def test_generate_json_schemas_for_domain_models() -> None:
    schemas = generate_json_schemas()

    assert "job_create" in schemas
    assert "assign_result" in schemas
    assert "properties" in schemas["job_create"]
    assert "required" in schemas["job_create"]


def test_assign_result_schema_contains_propensity_constraints() -> None:
    schema = generate_json_schemas()["assign_result"]
    propensity = schema["properties"]["propensity"]

    assert propensity["exclusiveMinimum"] == 0
    assert propensity["maximum"] == 1
