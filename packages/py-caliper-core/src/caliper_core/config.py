from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(StrEnum):
    EMBEDDED = "embedded"
    SERVICE = "service"
    SHARED = "shared"


class CaliperSettings(BaseSettings):
    """Runtime settings shared by embedded and service modes."""

    model_config = SettingsConfigDict(
        env_prefix="CALIPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    profile: Profile = Profile.EMBEDDED
    db_url: str | None = None
    data_dir: Path = Path("./data")
    reports_dir: Path = Path("./reports")
    exports_dir: Path = Path("./exports")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    auth_enabled: bool = False
    default_workspace_id: str = Field(default="ws_default")

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        if self.profile is Profile.EMBEDDED:
            return "sqlite:///./data/caliper.db"
        return "postgresql+psycopg://postgres:postgres@localhost:5432/caliper"


def load_settings(*, use_cache: bool = True) -> CaliperSettings:
    if use_cache:
        return _cached_settings()
    return CaliperSettings()


@lru_cache(maxsize=1)
def _cached_settings() -> CaliperSettings:
    return CaliperSettings()
