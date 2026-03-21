from __future__ import annotations

from fastapi import FastAPI

from apps.api.routers.arms import router as arms_router
from apps.api.routers.autotune import router as autotune_router
from apps.api.routers.decisions import router as decisions_router
from apps.api.routers.jobs import router as jobs_router
from apps.api.routers.reports import router as reports_router
from apps.api.routers.system import router as system_router
from apps.api.services.autotune import (
    autotune_disposition as _autotune_disposition,
)
from apps.api.services.autotune import (
    derived_complexity_score as _derived_complexity_score,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Caliper API", version="0.1.0")
    app.include_router(system_router)
    app.include_router(autotune_router)
    app.include_router(jobs_router)
    app.include_router(decisions_router)
    app.include_router(reports_router)
    app.include_router(arms_router)
    return app


app = create_app()

__all__ = ["_autotune_disposition", "_derived_complexity_score", "app", "create_app"]
