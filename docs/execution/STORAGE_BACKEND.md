# Storage Backends (SQLite + Postgres)

This chunk wires core repository interfaces to concrete SQL-backed implementations in
`caliper_storage`.

## Implemented in P1-002

- `SQLiteRepository` implements these `caliper_core.interfaces` protocols:
  - `JobRepository`
  - `ArmRepository`
  - `DecisionRepository`
  - `ExposureRepository`
  - `OutcomeRepository`
- SQLAlchemy session lifecycle is centralized with automatic commit/rollback behavior.
- Mapping helpers convert SQLAlchemy rows to/from Pydantic domain models.

## Implemented in P1-003

- Added backend-agnostic `SQLRepository` base implementation with backend facades:
  - `SQLiteRepository`
  - `PostgresRepository`
- Added lightweight migration support in `caliper_storage.migrations`:
  - `upgrade(engine)` applies baseline schema
  - stamps `schema_migrations` with `MIGRATION_VERSION`
- Expanded Postgres integration tests to validate repository parity and service-profile
  engine boot against Postgres.
- Added Docker Compose profile for local service-mode Postgres runs.

## Usage

```python
from caliper_storage import (
    PostgresRepository,
    SQLiteRepository,
    build_engine,
    init_db,
    make_session_factory,
)

# SQLite
sqlite_engine = build_engine("sqlite+pysqlite:///:memory:")
init_db(sqlite_engine)
sqlite_repo = SQLiteRepository(make_session_factory(sqlite_engine))

# Postgres
pg_engine = build_engine("postgresql+psycopg://postgres:postgres@localhost:5432/caliper")
init_db(pg_engine)
pg_repo = PostgresRepository(make_session_factory(pg_engine))
```

## Notes

- SQLite URLs use `check_same_thread=False` via `build_engine` for compatibility with app/threaded use.
- Migration support is intentionally minimal for this phase to keep schema initialization deterministic
  across both backends while preserving an explicit migration stamp.
