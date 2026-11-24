"""Start FastAPI and connect page routes, templates, static files, and APIs."""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import tiger_auth
from routers import (
    tiger_accounts,
    tiger_catalog,
    tiger_dashboard,
    tiger_friends,
    tiger_planning,
    tiger_profiles,
    tiger_schedules,
)
from tiger_views import APP_DIR

app: FastAPI = FastAPI(title="Tiger Class Drive")
app.add_exception_handler(
    tiger_auth.LoginRequired, tiger_auth.login_redirect
)
app.mount(
    "/static", StaticFiles(directory=str(APP_DIR / "static")), name="static"
)
app.include_router(tiger_catalog.router)
app.include_router(tiger_dashboard.router)
app.include_router(tiger_planning.router)
app.include_router(tiger_accounts.router)
app.include_router(tiger_profiles.router)
app.include_router(tiger_schedules.router)
app.include_router(tiger_friends.router)


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
