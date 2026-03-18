from __future__ import annotations

from pathlib import Path

from caliper_core.models import (
    ArmBulkRegisterRequest,
    ArmInput,
    ArmType,
    GuardrailSpec,
    Job,
    ObjectiveSpec,
    PolicyFamily,
    PolicySpec,
    SurfaceType,
)
from caliper_sdk import EmbeddedCaliperClient
from caliper_storage import SQLRepository, build_engine, make_session_factory
from fastapi.testclient import TestClient

from apps.demo_web.main import DemoWebConfig, create_app


def test_demo_web_server_tracks_render_click_conversion_and_report(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'demo-web.db'}"
    client = EmbeddedCaliperClient(db_url=db_url)

    job = Job(
        workspace_id="ws-demo-web",
        name="Demo web test",
        surface_type=SurfaceType.WEB,
        objective_spec=ObjectiveSpec(reward_formula="(0.4 * click) + conversion"),
        guardrail_spec=GuardrailSpec(rules=[]),
        policy_spec=PolicySpec(
            policy_family=PolicyFamily.FIXED_SPLIT,
            params={"weights": {"landing-0": 1.0, "landing-1": 1.0}},
        ),
    )
    created = client.create_job(job)
    job_id = created.job_id if isinstance(created, Job) else created["job_id"]

    variants_dir = tmp_path / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    variant_manifest: dict[str, str] = {}
    arms: list[ArmInput] = []
    for idx in range(2):
        arm_id = f"landing-{idx}"
        variant_path = variants_dir / f"{arm_id}.html"
        variant_path.write_text(
            f"<html><body><h1>Variant {idx}</h1><a href='{{{{CTA_URL}}}}'>CTA</a></body></html>",
            encoding="utf-8",
        )
        variant_manifest[arm_id] = str(variant_path.resolve())
        arms.append(
            ArmInput(
                arm_id=arm_id,
                name=f"Variant {idx}",
                arm_type=ArmType.ARTIFACT,
                payload_ref=f"file://{variant_path.resolve()}",
                metadata={"idx": idx},
            )
        )

    client.add_arms(
        job_id=job_id,
        payload=ArmBulkRegisterRequest(workspace_id=job.workspace_id, arms=arms),
    )

    app = create_app(
        DemoWebConfig(
            backend="embedded",
            workspace_id=job.workspace_id,
            job_id=job_id,
            topic="Demo topic",
            variant_manifest=variant_manifest,
            db_url=db_url,
        )
    )

    with TestClient(app) as http:
        landing = http.get(f"/lp/{job_id}")
        assert landing.status_code == 200
        assert "Variant" in landing.text

        click = http.get(f"/lp/{job_id}/click", follow_redirects=False)
        assert click.status_code == 302
        assert click.headers["location"].startswith(f"/lp/{job_id}/offer")

        offer = http.get(click.headers["location"])
        assert offer.status_code == 200
        assert "Complete conversion" in offer.text

        convert = http.post(f"/lp/{job_id}/convert")
        assert convert.status_code == 200
        assert "conversion logged" in convert.text.lower()

        report = http.get(f"/lp/{job_id}/report")
        assert report.status_code == 200
        payload = report.json()
        assert payload["job_id"] == job_id
        assert "leaders" in payload

    engine = build_engine(db_url)
    repository = SQLRepository(make_session_factory(engine))
    exposures = repository.list_exposures(job.workspace_id, job_id)
    outcomes = repository.list_outcomes(job.workspace_id, job_id)

    assert len(exposures) >= 1
    assert len(outcomes) >= 2

    outcome_types: list[str] = []
    for outcome in outcomes:
        for event in outcome.events:
            outcome_types.append(event.outcome_type)

    assert "click" in outcome_types
    assert "conversion" in outcome_types
