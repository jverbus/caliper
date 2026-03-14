from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(StrEnum):
    EMBEDDED = "embedded"
    SERVICE = "service"
    SHARED = "shared"


class CaliperSettings(BaseSettings):
    """Profile-aware runtime settings for embedded/service/shared deployments."""

    model_config = SettingsConfigDict(
        env_prefix="CALIPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    profile: Profile = Profile.EMBEDDED

    # Shared paths
    data_dir: Path = Path("./data")
    reports_dir: Path = Path("./reports")
    exports_dir: Path = Path("./exports")

    # API service
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database selection
    db_url: str | None = None
    sqlite_path: Path = Path("./data/caliper.db")
    postgres_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/caliper"

    # Shared mode controls
    auth_enabled: bool = False
    default_workspace_id: str = "ws_default"
    shared_api_token: SecretStr | None = None

    def resolved_db_url(self) -> str:
        """Resolve backend URL based on explicit override and active profile."""
        if self.db_url:
            return self.db_url
        if self.profile is Profile.EMBEDDED:
            return f"sqlite:///{self.sqlite_path.as_posix()}"
        return self.postgres_url

    def with_profile_defaults(self) -> CaliperSettings:
        """Return a settings copy with profile defaults normalized."""
        updates: dict[str, object] = {}

        if self.profile is Profile.EMBEDDED:
            updates["auth_enabled"] = False
        elif self.profile is Profile.SERVICE:
            updates["auth_enabled"] = bool(self.auth_enabled)
        elif self.profile is Profile.SHARED:
            updates["auth_enabled"] = True

        return self.model_copy(update=updates)

    def ensure_runtime_dirs(self) -> None:
        """Create local artifact directories for embedded/service runs."""
        for path in (self.data_dir, self.reports_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(*, use_cache: bool = True) -> CaliperSettings:
    if use_cache:
        return _cached_settings()
    return CaliperSettings().with_profile_defaults()


@lru_cache(maxsize=1)
def _cached_settings() -> CaliperSettings:
    return CaliperSettings().with_profile_defaults()
