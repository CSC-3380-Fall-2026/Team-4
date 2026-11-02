"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from lucide import lucide_icon

import tiger_auth  # Import by using filename.
import tiger_catalog
import tiger_dashboard
import tiger_gpa

app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=str(tiger_dashboard.APP_DIR / "static")),
    name="static"
)

app.include_router(tiger_dashboard.router)
app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)

def redirect_to_panel(request: Request, panel: str = "") -> RedirectResponse:
    return RedirectResponse(url=tiger_dashboard.panel_url(request, panel), status_code=303)


@app.get("/health")
def health():
    return {"healthy"}


@app.get("/")
async def root(request: Request) -> RedirectResponse:
    return redirect_to_panel(request)


@app.get("/schedule")
async def schedule(request: Request) -> RedirectResponse:
    return redirect_to_panel(request, "schedule")


@app.get("/planning")
async def planning(request: Request) -> RedirectResponse:
    return redirect_to_panel(request, "planning")


@app.get("/friends")
async def friends(request: Request) -> RedirectResponse:
    return redirect_to_panel(request, "friends")


@app.get("/profile")
async def profile(request: Request) -> RedirectResponse:
    return redirect_to_panel(request, "profile")


@app.get("/catalog")
async def catalog(request: Request) -> RedirectResponse:
    return RedirectResponse(url=request.url_for("dashboard_catalog"), status_code=303)

# Icons
@app.get("/icons/{icon_name}")
def get_icon(icon_name: str, size: int = 24, color: str = "currentColor"):
    svg = lucide_icon(icon_name, width=size, height=size, stroke=color)
    return Response(content=svg, media_type="image/svg+xml")
