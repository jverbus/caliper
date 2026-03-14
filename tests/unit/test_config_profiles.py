from __future__ import annotations

from pathlib import Path

from caliper_core import CaliperSettings, Profile


def test_embedded_profile_defaults_to_sqlite() -> None:
    settings = CaliperSettings(profile=Profile.EMBEDDED).with_profile_defaults()

    assert settings.auth_enabled is False
    assert settings.resolved_db_url() == "sqlite:///data/caliper.db"


def test_service_profile_defaults_to_postgres() -> None:
    settings = CaliperSettings(profile=Profile.SERVICE).with_profile_defaults()

    assert settings.resolved_db_url() == settings.postgres_url


def test_shared_profile_forces_auth_enabled() -> None:
    settings = CaliperSettings(profile=Profile.SHARED, auth_enabled=False).with_profile_defaults()

    assert settings.auth_enabled is True
    assert settings.resolved_db_url() == settings.postgres_url


def test_explicit_db_url_override_wins() -> None:
    settings = CaliperSettings(
        profile=Profile.EMBEDDED,
        db_url="postgresql+psycopg://custom/custom",
    ).with_profile_defaults()

    assert settings.resolved_db_url() == "postgresql+psycopg://custom/custom"


def test_runtime_dirs_created(tmp_path: Path) -> None:
    settings = CaliperSettings(
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "exports",
    ).with_profile_defaults()

    settings.ensure_runtime_dirs()

    assert settings.data_dir.is_dir()
    assert settings.reports_dir.is_dir()
    assert settings.exports_dir.is_dir()
