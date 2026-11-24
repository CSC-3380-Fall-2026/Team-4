"""Start FastAPI and connect page routes, templates, static files, and APIs."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from lucide import lucide_icon

import tiger_auth
from routers import (
    tiger_accounts,
    tiger_catalog,
    tiger_dashboard,
    tiger_free_time,
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
app.include_router(tiger_free_time.router)
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


@app.get("/icons/{icon_name}")
def get_icon(icon_name: str, size: int = 24) -> Response:
    """Serve one of the navigation SVG icons at a bounded size.

    Args:
        icon_name: Supported Lucide icon name.
        size: Requested width and height from 12 to 64 pixels.

    Returns:
        An SVG response for a supported icon.

    Raises:
        HTTPException: If the icon or size is unsupported.
    """
    allowed: set[str] = {
        "layout-dashboard",
        "calendar",
        "bookmark",
        "users",
        "user",
        "search",
        "plus",
        "chevron-down",
        "bell",
    }
    if icon_name not in allowed or not 12 <= size <= 64:
        raise HTTPException(404, "Icon not found.")
    return Response(
        lucide_icon(icon_name, width=size, height=size),
        media_type="image/svg+xml",
    )
