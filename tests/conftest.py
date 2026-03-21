from __future__ import annotations

import pytest

from caliper_storage.engine import dispose_tracked_engines


@pytest.fixture(autouse=True)
def _dispose_tracked_sqlalchemy_engines() -> None:
    yield
    dispose_tracked_engines()
