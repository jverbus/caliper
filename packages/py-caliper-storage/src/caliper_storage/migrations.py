from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from caliper_storage.sqlalchemy_models import Base

MIGRATION_VERSION = "p1_003"


def upgrade(engine: Engine) -> None:
    """Apply baseline schema and record migration version.

    This lightweight migration hook keeps service boot deterministic for both
    SQLite and Postgres until a full revisioned migration stack is introduced.
    """

    Base.metadata.create_all(bind=engine)
    _ensure_jobs_columns(engine)
    _ensure_migration_table(engine)
    _stamp_version(engine)


def _ensure_jobs_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "approval_state" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE jobs ADD COLUMN approval_state "
                    "VARCHAR(32) NOT NULL DEFAULT 'not_required'"
                )
            )


def _ensure_migration_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if "schema_migrations" in inspector.get_table_names():
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _stamp_version(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO schema_migrations (version) VALUES (:version) ON CONFLICT DO NOTHING"
            ),
            {"version": MIGRATION_VERSION},
        )
