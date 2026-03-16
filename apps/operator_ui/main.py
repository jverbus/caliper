from __future__ import annotations

from html import escape
from typing import Annotated

from caliper_storage.repositories import SQLRepository
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.api.dependencies import get_repository


def create_app() -> FastAPI:
    app = FastAPI(title="Caliper Operator UI", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=RedirectResponse)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/jobs", status_code=302)

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(
        repository: Annotated[SQLRepository, Depends(get_repository)],
        workspace_id: str | None = None,
    ) -> HTMLResponse:
        jobs = repository.list_jobs(workspace_id=workspace_id)

        rows = "".join(
            ""
            "<tr>"
            f"<td><code>{escape(job.job_id)}</code></td>"
            f"<td>{escape(job.workspace_id)}</td>"
            f"<td>{escape(job.name)}</td>"
            f"<td>{escape(job.surface_type.value)}</td>"
            f"<td>{escape(job.status.value)}</td>"
            f"<td>{escape(job.approval_state.value)}</td>"
            "</tr>"
            for job in jobs
        )

        if not rows:
            rows = (
                "<tr><td colspan='6'>No jobs found. Create a job via API/CLI and refresh.</td></tr>"
            )

        workspace_filter = workspace_id or "all"
        html = f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Caliper Operator UI</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; }}
      h1 {{ margin-bottom: 0.5rem; }}
      .meta {{ color: #555; margin-bottom: 1rem; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
      th {{ background: #f7f7f7; }}
      code {{ font-size: 0.9em; }}
    </style>
  </head>
  <body>
    <h1>Caliper Operator UI</h1>
    <div class=\"meta\">workspace filter: <strong>{escape(workspace_filter)}</strong></div>
    <table>
      <thead>
        <tr>
          <th>Job ID</th>
          <th>Workspace</th>
          <th>Name</th>
          <th>Surface</th>
          <th>Status</th>
          <th>Approval</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </body>
</html>
"""
        return HTMLResponse(content=html)

    return app


app = create_app()
