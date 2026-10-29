from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from lucide import lucide_icon
from markupsafe import Markup

from tiger_catalog import load_courses, search_courses


router: APIRouter = APIRouter()

APP_DIR: Path = Path(__file__).resolve().parent

templates: Jinja2Templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)
class DashboardFriend:
    def __init__(
        self,
        friend_id: int,
        name: str,
        status: str,
        available: bool,
    ) -> None:
        self.id: int = friend_id
        self.name: str = name
        self.status: str = status
        self.available: bool = available
SAMPLE_FRIENDS: list[DashboardFriend] = [
    DashboardFriend(1, "User", "Free now", True),
    DashboardFriend(2, "User", "Busy (Class)", False),
    DashboardFriend(3, "User", "Busy (Work)", False),
    DashboardFriend(4, "User", "Busy (Gym)", False),
]
def page_context(request: Request) -> dict[str, object]:
    icon_names: list[str] = [
        "layout-dashboard",
        "calendar",
        "bookmark",
        "users",
        "user",
        "bell",
    ]

    icons: dict[str, Markup] = {}
    for name in icon_names:
        icons[name] = Markup(
            lucide_icon(
                name,
                width=20,
                height=20,
                stroke="currentColor",
            )
        )
    links: list[dict[str, str]] = [
        {
            "label": "Dashboard",
            "href": "/dashboard",
            "icon": "layout-dashboard",
        },
        {
            "label": "My Schedule",
            "href": "/dashboard?panel=schedule",
            "icon": "calendar",
        },
        {
            "label": "Planning",
         "href": "/dashboard?panel=planning",
            "icon": "bookmark",
        },
        {
            "label": "Friends",
            "href": "/dashboard?panel=friends",
            "icon": "users",
        },
        {
            "label": "Profile",
            "href": "/dashboard?panel=profile",
            "icon": "user",
        },
    ]
    return {
        "request": request,
        "icons": icons,
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
        "catalog_href": "/dashboard/catalog",
    }
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    panel: str = "",
    sample: bool = False,
    preview_ping: int | None = None,
) -> HTMLResponse:
    context: dict[str, object] = page_context(request)

    # Explain features that have not been connected yet.
    if panel == "schedule":
        context["notice"] = (
            "Scheduels are not currently avaliable to be saved "
            "You will be able to calculate gpa now "
        )
    elif panel == "friends":
        context["notice"] = (
            "You are unable to make friend request "
            "No data for friends yet"
        )

    elif panel == "profile":
        context["notice"] = (
            "No Account profiles are connected to the dashboard. "
            "No infromation has been loaded yet"
        )
    if sample:
        context["sample"] = True
        context["friends"] = SAMPLE_FRIENDS
        for friend in SAMPLE_FRIENDS:
            if preview_ping == friend.id:
                context["pinged"] = friend.id
                context["notice"] = (
                    "Has been reviewed "
                    "Invalid no messege has been sent yet"
                )
                break
    return templates.TemplateResponse(
        request=request,
        name="tiger_dashboard.html",
        context=context,
    )
@router.get("/dashboard/catalog", response_class=HTMLResponse)
def dashboard_catalog(
    request: Request,
    query: str = "",
    category: str = "",
) -> HTMLResponse:
    context: dict[str, object] = page_context(request)
    categories: list[str] = []
    for course in load_courses():
        course_category: str = course["category"]
        if course_category not in categories:
            categories.append(course_category)
    categories.sort()
    context["catalog_mode"] = True
    context["courses"] = search_courses(
        query=query,
        category=category,
    )
    context["query"] = query
    context["category"] = category
    context["categories"] = categories

    return templates.TemplateResponse(
        request=request,
        name="tiger_dashboard.html",
        context=context,
    )
