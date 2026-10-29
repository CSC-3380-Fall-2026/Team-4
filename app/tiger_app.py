"""this file will be for starting the fasTAPI and connecting page routes and templates and static files."""
"""PLEASE set up a .VENV look under # How to Run Dev and Test Environment in the README.md"""
from fastapi import FastAPI, Request
from fastapi.responses import Response, HTMLResponse
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

#Home
@app.get("/", response_class=HTMLResponse)
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
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Login
@app.get("/login", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_login.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Signin
@app.get("/signin", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_signin.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_dashboard.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Schedule
@app.get("/schedule", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_schedule.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Planning
@app.get("/planning", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_planner.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Friends
@app.get("/friends", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_friends.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
        },
    )

#Profile
@app.get("/profile", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request,
        "tiger_profile.html",
        {
            "name": "willyt",
            "dashboard": Markup(dashboard),
            "calendar": Markup(calendar),
            "bookmark": Markup(bookmark),
            "users": Markup(users),
            "user": Markup(user),
            "search": Markup(search),
            "plus": Markup(plus),
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
search = lucide_icon("search", width=18, height=18, stroke="currentColor")
plus = lucide_icon("plus", width=18, height=18, stroke="currentColor")
