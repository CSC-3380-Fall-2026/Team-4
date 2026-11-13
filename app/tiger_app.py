"""Start FastAPI and connect page routes, templates, static files, and APIs."""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import tiger_auth
import tiger_catalog
import tiger_gpa
from routers import tiger_accounts, tiger_pages, tiger_planning
from tiger_views import APP_DIR

app: FastAPI = FastAPI(title="Tiger Class Drive")
app.mount(
    "/static", StaticFiles(directory=str(APP_DIR / "static")), name="static"
)
app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)
app.include_router(tiger_pages.router)
app.include_router(tiger_planning.router)
app.include_router(tiger_accounts.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the web application is running.

    Returns:
        A health status independent of optional account-service credentials.
    """
    return {"status": "healthy"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Serve the project mark when a browser asks for a favicon.

    Returns:
        The same SVG mark used for the site's browser icon.
    """
    return FileResponse(
        APP_DIR / "static" / "tiger_icon.svg", media_type="image/svg+xml"
    )
