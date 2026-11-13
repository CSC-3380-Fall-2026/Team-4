"""Connect page URLs without changing the existing catalog or GPA API URLs."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lucide import lucide_icon

import tiger_auth
import tiger_catalog
from models.tiger_dashboard import DashboardData
from tiger_dashboard import dashboard_data
from tiger_views import render_page

router: APIRouter = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request) -> RedirectResponse:
    """Open the dashboard from the site's root address.

    Args:
        request: Browser request for the site's root.

    Returns:
        A redirect to the canonical dashboard URL.
    """
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    """Display selected schedule, GPA forecast, and upcoming event sections.

    Args:
        request: Browser request used by the configured data provider.

    Returns:
        William's layout populated with actual supplied values or empty states.
    """
    data: DashboardData = dashboard_data(request)
    return render_page(request, "tiger_dashboard.html", data=data)


@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(request: Request) -> HTMLResponse:
    """Open the schedule page using the same supplied data as the dashboard.

    Args:
        request: Browser request used to load available schedule information.

    Returns:
        A schedule page with the current week's headings and provided events.
    """
    today: datetime = datetime.now(ZoneInfo("America/Chicago"))
    week_start: datetime = today - timedelta(days=today.weekday())
    week_days: list[dict[str, str]] = []
    for index in range(7):
        day: datetime = week_start + timedelta(days=index)
        week_days.append(
            {"name": day.strftime("%a"), "date": day.strftime("%b %d")}
        )
    return render_page(
        request,
        "tiger_schedule.html",
        data=dashboard_data(request),
        week_days=week_days,
    )


@router.get("/friends", response_class=HTMLResponse)
def friends_page(request: Request) -> HTMLResponse:
    """Open the Friends layout without presenting sample accounts as real users.

    Args:
        request: Browser request for the Friends page.

    Returns:
        Navigation and clear empty states for features awaiting the friend backend.
    """
    return render_page(request, "tiger_friends.html")


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request) -> HTMLResponse:
    """Display only the browser's verified account and available profile data.

    Args:
        request: Browser request with an optional account cookie.

    Returns:
        A profile, sign-in prompt, or understandable service error.
    """
    profile: dict[str, Any] | None = None
    error: str = ""
    try:
        profile = tiger_auth.load_profile(request)
    except HTTPException as exception:
        error = str(exception.detail)
    return render_page(
        request,
        "tiger_profile.html",
        profile=profile,
        error=error,
        status_code=503 if error else 200,
    )


@router.get("/catalog", response_class=HTMLResponse)
def catalog_page(
    request: Request,
    query: str = "",
    category: str = "",
) -> HTMLResponse:
    """Display the existing catalog search results inside shared navigation.

    Args:
        request: Browser request for the catalog.
        query: Course-code or course-name search text.
        category: Optional category selected in the form.

    Returns:
        An HTML result page with filters retained when errors occur.
    """
    courses: list[dict[str, object]] = []
    categories: list[str] = []
    error: str = ""
    status_code: int = 200
    try:
        categories = sorted(
            {course["category"] for course in tiger_catalog.load_courses()}
        )
        if len(query) > 100:
            raise HTTPException(
                400, "Keep your search to 100 characters or fewer."
            )
        if category and category not in categories:
            raise HTTPException(400, "Choose a category from the dropdown.")
        courses = tiger_catalog.search_courses(query=query, category=category)
    except HTTPException as exception:
        error = (
            str(exception.detail)
            if exception.status_code == 400
            else (
                "The course catalog is temporarily unavailable. Please try again later."
            )
        )
        status_code = exception.status_code
    return render_page(
        request,
        "tiger_catalog.html",
        courses=courses,
        categories=categories,
        query=query,
        category=category,
        error=error,
        status_code=status_code,
    )


@router.get("/icons/{icon_name}")
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
