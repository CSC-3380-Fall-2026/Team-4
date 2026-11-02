from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from lucide import lucide_icon
from markupsafe import Markup
from starlette.datastructures import URL
from tiger_models import DashboardFriend
from tiger_catalog import filter_courses, load_courses


router: APIRouter = APIRouter()

APP_DIR: Path = Path(__file__).resolve().parent

templates: Jinja2Templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

SAMPLE_FRIENDS: list[DashboardFriend] = [
    DashboardFriend(1, "User", "Free now", True),
    DashboardFriend(2, "User", "Busy (Class)", False),
    DashboardFriend(3, "User", "Busy (Work)", False),
    DashboardFriend(4, "User", "Busy (Gym)", False),
]

# (label, panel, icon) for each sidebar link. An empty panel is the main dashboard.
NAV_LINKS: list[tuple[str, str, str]] = [
    ("Dashboard", "", "layout-dashboard"),
    ("My Schedule", "schedule", "calendar"),
    ("Planning", "planning", "bookmark"),
    ("Friends", "friends", "users"),
    ("Profile", "profile", "user"),
]

# Explain features that have not been connected yet.
PANEL_NOTICES: dict[str, str] = {
    "schedule": (
        "Schedules are not currently available to be saved. "
        "You will be able to calculate GPA now."
    ),
    "planning": "The GPA Planning form has not been connected yet.",
    "friends": (
        "You are unable to make friend requests. "
        "No data for friends yet."
    ),
    "profile": (
        "No account profiles are connected to the dashboard. "
        "No information has been loaded yet."
    ),
}

# The icons never change, so render them once instead of on every request.
ICONS: dict[str, Markup] = {
    name: Markup(lucide_icon(name, width=20, height=20, stroke="currentColor"))
    for name in [icon for _, _, icon in NAV_LINKS] + ["bell"]
}


def panel_url(request: Request, panel: str = "") -> URL:
    # Build hrefs from route names so they follow the routes if paths change.
    url = request.url_for("dashboard")
    return url.include_query_params(panel=panel) if panel else url


def page_context(request: Request) -> dict[str, object]:
    links: list[dict[str, str]] = [
        {"label": label, "href": str(panel_url(request, panel)), "icon": icon}
        for label, panel, icon in NAV_LINKS
    ]
    return {
        "icons": ICONS,
        "links": links,
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "times": [
            "09:00 AM",
            "11:00 AM",
            "01:00 PM",
            "03:00 PM",
            "05:00 PM",
            "07:00 PM",
        ],
        "friends": [],
        "sample": False,
        "planning_mode": False,
        "catalog_mode": False,
        "notice": "",
        "pinged": None,
    }


def render_dashboard(request: Request, context: dict[str, object]) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="tiger_dashboard.html",
        context=context,
    )


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
def dashboard(
    request: Request,
    panel: str = "",
    sample: bool = False,
    preview_ping: int | None = None,
) -> HTMLResponse:
    context: dict[str, object] = page_context(request)
    context["notice"] = PANEL_NOTICES.get(panel, "")

    if sample:
        context["sample"] = True
        context["friends"] = SAMPLE_FRIENDS
        if preview_ping in {friend.id for friend in SAMPLE_FRIENDS}:
            context["pinged"] = preview_ping
            context["notice"] = (
                "Has been reviewed. "
                "Invalid, no message has been sent yet."
            )
    return render_dashboard(request, context)


@router.get(
    "/dashboard/catalog",
    response_class=HTMLResponse,
    name="dashboard_catalog",
)
def dashboard_catalog(
    request: Request,
    query: str = "",
    category: str = "",
) -> HTMLResponse:
    courses: list[dict] = load_courses()
    context: dict[str, object] = page_context(request)
    context["catalog_mode"] = True
    context["courses"] = filter_courses(courses, query, category)
    context["query"] = query
    context["category"] = category
    context["categories"] = sorted({course["category"] for course in courses})
    return render_dashboard(request, context)
