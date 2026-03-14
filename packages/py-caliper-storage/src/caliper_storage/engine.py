from __future__ import annotations

from caliper_core.config import CaliperSettings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from caliper_storage.migrations import upgrade


def build_engine(db_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, future=True, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    upgrade(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_engine_from_settings(settings: CaliperSettings) -> Engine:
    engine = build_engine(settings.resolved_db_url())
    init_db(engine)
    return engine
