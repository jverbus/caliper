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
    job_id = created.job_id

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
        assert "browser_tracker.js" in landing.text
        assert "operator_panel.js" in landing.text
        first_visitor_id = http.cookies.get("caliper_visitor_id")
        assert first_visitor_id is not None

        landing_no_tracker = http.get(f"/lp/{job_id}?browser_tracker=0")
        assert landing_no_tracker.status_code == 200
        assert "browser_tracker.js" not in landing_no_tracker.text
        assert "operator_panel.js" in landing_no_tracker.text

        forced_new_visitor = http.get(
            f"/lp/{job_id}?force_new_visitor=1&operator_action=force_new_visitor"
        )
        assert forced_new_visitor.status_code == 200
        forced_visitor_id = http.cookies.get("caliper_visitor_id")
        assert forced_visitor_id is not None
        assert forced_visitor_id != first_visitor_id

        click = http.get(f"/lp/{job_id}/click", follow_redirects=False)
        assert click.status_code == 302
        assert click.headers["location"].startswith(f"/lp/{job_id}/offer")

        offer = http.get(click.headers["location"])
        assert offer.status_code == 200
        assert "Complete conversion" in offer.text

        convert = http.post(f"/lp/{job_id}/convert")
        assert convert.status_code == 200
        assert "conversion logged" in convert.text.lower()

        telemetry = http.post(
            f"/lp/{job_id}/events",
            json={
                "events": [
                    {
                        "event_type": "time_spent",
                        "event_id": "evt-time-1",
                        "value": 6.25,
                        "metadata": {
                            "measurement": "visible_time",
                            "reason": "test",
                        },
                    },
                    {
                        "event_type": "click_detail",
                        "event_id": "evt-click-1",
                        "value": 1.0,
                        "metadata": {
                            "tag": "a",
                            "text": "Learn more",
                            "caliper_click_role": "cta_primary",
                        },
                    },
                ]
            },
        )
        assert telemetry.status_code == 200
        telemetry_payload = telemetry.json()
        assert telemetry_payload["accepted"] == 2
        assert telemetry_payload["ignored_duplicates"] == 0

        telemetry_retry = http.post(
            f"/lp/{job_id}/events",
            json={
                "events": [
                    {
                        "event_type": "time_spent",
                        "event_id": "evt-time-1",
                        "value": 6.25,
                    }
                ]
            },
        )
        assert telemetry_retry.status_code == 200
        retry_payload = telemetry_retry.json()
        assert retry_payload["accepted"] == 0
        assert retry_payload["ignored_duplicates"] == 1

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
    assert len(outcomes) >= 4

    assert any(exposure.metadata.get("force_new_visitor") is True for exposure in exposures)
    assert any(
        exposure.metadata.get("operator_action") == "force_new_visitor" for exposure in exposures
    )

    outcome_types: list[str] = []
    browser_tracker_outcomes = []
    for outcome in outcomes:
        if outcome.metadata.get("source") == "browser_tracker":
            browser_tracker_outcomes.append(outcome)
        for event in outcome.events:
            outcome_types.append(event.outcome_type)

    assert "click" in outcome_types
    assert "conversion" in outcome_types
    assert "click_detail" in outcome_types
    assert "time_spent" in outcome_types

    assert browser_tracker_outcomes
    assert any(
        outcome.metadata.get("browser_event_type") == "time_spent"
        for outcome in browser_tracker_outcomes
    )
