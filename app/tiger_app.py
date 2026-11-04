"""Start FastAPI and connect page routes, templates, and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from lucide import lucide_icon
from markupsafe import Markup
from tiger_models import *
from pathlib import Path
import tiger_catalog
import tiger_auth  # Import by using filename. 
import tiger_gpa


app = FastAPI()



templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)

app_dir: Path = Path(__file__).resolve().parent
app.mount(
    "/static",
    StaticFiles(directory=str(app_dir / "static")),
    name="static",
)


app.include_router(tiger_auth.router)
app.include_router(tiger_gpa.router)
app.include_router(tiger_catalog.router)

@app.get("/health")
def health():
    return {"healthy"}

#Home
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_home.html")

#Login
@app.get("/login", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_login.html")

#Signin
@app.get("/signin", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_signin.html")

#Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_dashboard.html")

#Schedule
@app.get("/schedule", response_class=HTMLResponse)
async def get_calendar(request: Request):
    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())

    week_days = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        week_days.append({
            "name": day.strftime("%A"),
            "date_str": day.strftime("%b %d"),
            "is_today": day.date() == today.date()
        })

    return render_page(request, "tiger_schedule.html", week_days=week_days)


#Planning
@app.get("/planning", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_planner.html")

#Friends
@app.get("/friends", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_friends.html")

#Profile
@app.get("/profile", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_profile.html")

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
search = lucide_icon("search", width=18, height=18, stroke="currentColor")
plus = lucide_icon("plus", width=18, height=18, stroke="currentColor")
chevrondown = lucide_icon("plus", width=18, height=18, stroke="currentColor")


def render_page(request: Request, template_name: str, **context: object) -> Response:
    """Render a page with the shared user and navigation-icon template context."""
    page_context = {
        "name": "willyt",
        "dashboard": Markup(dashboard),
        "calendar": Markup(calendar),
        "bookmark": Markup(bookmark),
        "users": Markup(users),
        "user": Markup(user),
        "search": Markup(search),
        "plus": Markup(plus),
        "chevron-down": Markup(chevrondown),
    }
    page_context.update(context)
    return templates.TemplateResponse(request, template_name, page_context)
