import os

import pytest
from sqlalchemy import text


@pytest.mark.skipif(
    not os.getenv("CALIPER_DB_URL"),
    reason="CALIPER_DB_URL is required for postgres smoke test",
)
def test_postgres_connection_smoke() -> None:
    from caliper_storage.engine import build_engine

    db_url = os.environ["CALIPER_DB_URL"]
    engine = build_engine(db_url)
    with engine.connect() as connection:
        result = connection.execute(text("select 1"))
        assert result.scalar_one() == 1
