from __future__ import annotations

from caliper_core.interfaces import (
    ArmRepository,
    AuditRepository,
    DecisionRepository,
    EventLedger,
    ExposureRepository,
    GuardrailEventRepository,
    JobRepository,
    OutcomeRepository,
    ReportRepository,
)

from caliper_storage.repository_modules import (
    ArmDecisionRepositoryMixin,
    AutotuneRepositoryMixin,
    EventProjectionRepositoryMixin,
    JobAuditRepositoryMixin,
    TelemetryRepositoryMixin,
)


class SQLRepository(
    JobAuditRepositoryMixin,
    ArmDecisionRepositoryMixin,
    TelemetryRepositoryMixin,
    EventProjectionRepositoryMixin,
    AutotuneRepositoryMixin,
    JobRepository,
    ArmRepository,
    DecisionRepository,
    ExposureRepository,
    OutcomeRepository,
    GuardrailEventRepository,
    EventLedger,
    AuditRepository,
    ReportRepository,
):
    """SQLAlchemy-backed repository implementation for core domain models."""


class SQLiteRepository(SQLRepository):
    """SQLite-specific repository facade backed by SQLRepository."""


class PostgresRepository(SQLRepository):
    """Postgres-specific repository facade backed by SQLRepository."""
