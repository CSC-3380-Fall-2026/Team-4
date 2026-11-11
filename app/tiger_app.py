"""Start FastAPI and connect page routes, templates, and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, HTMLResponse, RedirectResponse 
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from lucide import lucide_icon
from markupsafe import Markup
from tiger_models import *
from pathlib import Path
import tiger_catalog
import tiger_scheduler

import tiger_auth  # Import by using filename. 
import tiger_gpa
from fastapi.responses import RedirectResponse
import tiger_prerequisites

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
app.include_router(tiger_prerequisites.router)
app.include_router(tiger_scheduler.router)

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
    return render_page(request, "Tiger_login.html")

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

#Catalog
@app.get("/catalog", response_class=HTMLResponse)
def catalog_page(request: Request, query: str ="", category: str = "",) -> Response: 
    """Display courses matching the submitted search and category."""

    query = query.strip()
    category = category.strip()

    courses: list[dict[str, object]]= []
    categories: list[str] = []
    error: str = ""
    status_code: int = 200

    try:
        categories = sorted({course["category"] for course in tiger_catalog.load_courses()})

        if len(query) > 100:
            error = "Keep the search to 100 characters or fewer please."
            status_code = 400

        elif category and category not in categories:
            error = "Choose a category from the dropdown."
            category = ""
            status_code = 400

        else:
            courses = tiger_catalog.search_courses(query=query, category=category)

    except HTTPException:
        error = ("Sorry, the course catalog could not be loaded." "Please try again later :).")
        status_code = 500
    return render_page(request, "tiger_catalog.html", courses=courses, categories=categories, query=query, category=category, error = error, status_code=status_code,)


#Friends
@app.get("/friends", response_class=HTMLResponse)
async def root(request: Request):
    return render_page(request, "tiger_friends.html")

#Profile
@app.get("/profile", response_class=HTMLResponse)
async def root(request: Request) -> Response:
    """Display the vertified student's profile without allowing edits."""

    profile: dict[str, object] | None = None
    profile_error: bool = False

    try:
        profile = tiger_auth.load_profile(request)

    except HTTPException:
        profile_error = True

    if profile is None and not profile_error:
        response: Response = RedirectResponse (url = "/login", status_code=303,)

    else:

        response = render_page(request, "tiger_profile.html", profile=profile, profile_error = profile_error)

        response.status_code = 503 if profile_error else 200

        response.header["Cache-Control"] = "no-store"

        return response 

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
