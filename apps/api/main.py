from __future__ import annotations

from typing import Annotated

from api.dependencies import get_engine, health_check, readiness_check, require_api_token
from fastapi import Depends, FastAPI
from sqlalchemy import Engine


def create_app() -> FastAPI:
    app = FastAPI(title="Caliper API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_check()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return health_check()

    @app.get("/readyz")
    def readyz(engine: Annotated[Engine, Depends(get_engine)]) -> dict[str, str]:
        return readiness_check(engine)

    @app.get("/v1/system/info", dependencies=[Depends(require_api_token)])
    def system_info() -> dict[str, str]:
        return {"service": "caliper-api", "api_version": "v1"}

    return app


app = create_app()
