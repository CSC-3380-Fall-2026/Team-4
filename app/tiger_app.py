"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from lucide import lucide_icon

import tiger_auth  # Import by using filename.
import tiger_catalog
import tiger_dashboard
import tiger_gpa

app = FastAPI()

APP_DIR: Path = Path(__file__).resolve().parent
templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)
app.mount(
    "/static",
    StaticFiles(directory=str(APP_DIR / "static")),
    name="static"
)

app.include_router(tiger_dashboard.router)
app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)

@app.get("/health")
def health():
    return {"healthy"}
@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/schedule")
async def schedule() -> RedirectResponse:
    return RedirectResponse(url="/dashboard?panel=schedule", status_code=303)


@app.get("/planning")
async def planning() -> RedirectResponse:
    return RedirectResponse(url="/dashboard?panel=planning", status_code=303)


@app.get("/friends")
async def friends() -> RedirectResponse:
    return RedirectResponse(url="/dashboard?panel=friends", status_code=303)


@app.get("/profile")
async def profile() -> RedirectResponse:
    return RedirectResponse(url="/dashboard?panel=profile", status_code=303)


@app.get("/catalog")
async def catalog() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/catalog", status_code=303)

# Icons
@app.get("/icons/{icon_name}")
def get_icon(icon_name: str, size: int = 24, color: str = "currentColor"):
    svg = lucide_icon(icon_name, width=size, height=size, stroke=color)
    return Response(content=svg, media_type="image/svg+xml")

dashboard = lucide_icon("layout-dashboard", width=18, height=18, stroke="currentColor")
calendar = lucide_icon("calendar", width=18, height=18, stroke="currentColor")
bookmark = lucide_icon("bookmark", width=18, height=18, stroke="currentColor")
users = lucide_icon("users", width=18, height=18, stroke="currentColor")
user = lucide_icon("user", width=18, height=18, stroke="currentColor")
