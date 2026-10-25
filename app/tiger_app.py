"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from lucide import lucide_icon
from markupsafe import Markup
from tiger_models import *
import tiger_catalog
import tiger_auth  # Import by using filename. 
import tiger_gpa


app = FastAPI()




templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)

@app.get("/health")
def health():
    return {"healthy"}

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_home.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
        },
    )

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
