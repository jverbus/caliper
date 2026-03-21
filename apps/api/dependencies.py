from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Annotated

from caliper_core.config import CaliperSettings, load_settings
from caliper_sdk import CaliperService
from caliper_storage import SQLRepository, init_engine_from_settings, make_session_factory
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_settings() -> CaliperSettings:
    settings = load_settings(use_cache=False)
    settings.ensure_runtime_dirs()
    return settings


@lru_cache(maxsize=1)
def _cached_engine() -> Engine:
    return init_engine_from_settings(get_settings())


def get_engine() -> Engine:
    return _cached_engine()


@lru_cache(maxsize=1)
def _cached_session_factory() -> sessionmaker[Session]:
    return make_session_factory(get_engine())


def get_session_factory() -> sessionmaker[Session]:
    return _cached_session_factory()


def get_repository(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> SQLRepository:
    return SQLRepository(session_factory)


def get_caliper_service(
    repository: Annotated[SQLRepository, Depends(get_repository)],
) -> CaliperService:
    return CaliperService(repository=repository)


def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[CaliperSettings, Depends(get_settings)],
) -> None:
    if not settings.auth_enabled:
        return

    configured_token = settings.shared_api_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shared API token is not configured.",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != configured_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def health_check() -> dict[str, str]:
    return {"status": "ok"}


def readiness_check(engine: Engine) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - exercised via failure path tests
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not ready: {exc}",
        ) from exc
    return {"status": "ready"}


def reset_dependency_caches() -> None:
    """Clear dependency caches and dispose any cached engine first."""
    if _cached_engine.cache_info().currsize:
        _cached_engine().dispose()
    _cached_session_factory.cache_clear()
    _cached_engine.cache_clear()
    get_settings.cache_clear()


def iter_request_scope() -> Generator[str, None, None]:
    """Placeholder dependency hook for request-scoped wiring in later chunks."""
    yield "request-scope"
