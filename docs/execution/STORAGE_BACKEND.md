# Storage Interfaces and SQLite Backend

This chunk wires core repository interfaces to a concrete SQLite-backed implementation in
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
- Existing schema initialization (`init_db`) remains the migration baseline for this phase.

## Usage

```python
from caliper_storage import SQLiteRepository, build_engine, init_db, make_session_factory

engine = build_engine("sqlite+pysqlite:///:memory:")
init_db(engine)
session_factory = make_session_factory(engine)
repo = SQLiteRepository(session_factory)
```

## Notes

- SQLite URLs use `check_same_thread=False` via `build_engine` for compatibility with app/threaded use.
- Postgres wiring remains in place through SQLAlchemy models and shared engine bootstrap, with dedicated
  backend feature parity targeted in P1-003.
