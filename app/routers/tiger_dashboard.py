"""Serve the page URLs, and build the dashboard from the student's saved data."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lucide import lucide_icon

import tiger_auth
from grade_scale import GRADE_POINTS
from models.tiger_catalog import CourseResult
from models.tiger_dashboard import (
    DashboardData,
    ScheduleSummary,
    UpcomingEvent,
)
from models.tiger_profiles import AccountCard
from models.tiger_schedules import WEEKDAYS, Classes, Schedule, ScheduleEvent
from models.tiger_session import Session
from routers import tiger_catalog
from routers.tiger_catalog import check_prerequisites
from routers.tiger_planning import read_forecast
from routers.tiger_schedules_store import current_semester, list_schedules
from tiger_auth import require_login, session_profile
from tiger_views import redirect_to, render_page

ZONE: ZoneInfo = ZoneInfo("America/Chicago")
WEEKS: int = 6
LIMIT: int = 6


def occurrence(event: ScheduleEvent, day: date) -> UpcomingEvent:
    """Place one event on a calendar day.

    Args:
        event: Schedule event with an HH:MM start time.
        day: Calendar date on which it meets.

    Returns:
        The event with a Chicago-time start.
    """
    return UpcomingEvent(
        title=event.title,
        starts_at=datetime.combine(day, time.fromisoformat(event.start), tzinfo=ZONE),
        location=event.location,
    )


def event_dates(event: ScheduleEvent, today: date) -> list[date]:
    """List the dates an event meets over the next few weeks.

    Args:
        event: Schedule event with weekday names.
        today: First date to consider.

    Returns:
        One date per meeting, starting from today.
    """
    dates: list[date] = []
    for name in event.days:
        ahead: int = (WEEKDAYS.index(name) - today.weekday()) % 7
        for week in range(WEEKS):
            dates.append(today + timedelta(days=ahead + 7 * week))
    return dates


def upcoming_events(
    schedules: list[Schedule], now: datetime
) -> list[UpcomingEvent]:
    """Find the next class and event meetings across saved schedules.

    Args:
        schedules: The student's saved schedules.
        now: Current time in America/Chicago.

    Returns:
        Up to six future meetings in time order.
    """
    found: list[UpcomingEvent] = []
    for schedule in schedules:
        for event in schedule.events:
            for day in event_dates(event, now.date()):
                found.append(occurrence(event, day))
    future = [item for item in found if item.starts_at >= now]
    return sorted(future, key=lambda item: item.starts_at)[:LIMIT]


def summarize(schedule: Schedule) -> ScheduleSummary:
    """Summarize a schedule's courses and credit hours.

    Args:
        schedule: The schedule to describe.

    Returns:
        Its name, semester, class count and stored credit hours.
    """
    classes = [item for item in schedule.events if isinstance(item, Classes)]
    return ScheduleSummary(
        name=schedule.name,
        semester=classes[0].semester if classes else current_semester(),
        credit_hours=sum(item.credit for item in classes),
        course_count=len(classes),
    )


def load_schedules(session: Session) -> list[Schedule]:
    """Read saved schedules, treating a database failure as no schedules.

    Args:
        session: Verified student and their database client.

    Returns:
        The student's schedules, or an empty list when unavailable.
    """
    try:
        return list_schedules(session)
    except Exception:
        return []


def dashboard_data(session: Session) -> DashboardData:
    """Collect the student's profile, schedules and forecast for display.

    Args:
        session: Verified student and their database client.

    Returns:
        Real saved values, with honest empty states for anything missing.
    """
    data: DashboardData = DashboardData(forecast=read_forecast(session))
    try:
        profile = session_profile(session)
        data.gpa = profile.gpa
        data.completed_hours = profile.completed_credit_hours
    except Exception:
        pass
    schedules: list[Schedule] = load_schedules(session)
    if schedules:
        data.selected = summarize(schedules[0])
    data.events = upcoming_events(schedules, datetime.now(ZONE))
    return data


def check_courses(course_code: str, completed: str) -> CourseResult:
    """Validate course entries and reuse the prerequisite checker.

    Args:
        course_code: Course code the student wants to check.
        completed: Completed courses in COURSE: GRADE format, one per line.

    Returns:
        Satisfied, missing, and unverified prerequisites for the course.

    Raises:
        ValueError: If a course, grade, or input format is invalid.
    """
    if len(course_code) > 100 or len(completed) > 5000:
        raise ValueError("Keep the course list to 5,000 characters or fewer.")
    course_code = " ".join(course_code.upper().split())
    if not course_code:
        raise ValueError("Enter the course you want to check.")
    grades: dict[str, str] = {}
    for line in completed.splitlines():
        if not line.strip():
            continue
        code, separator, grade = line.partition(":")
        code = " ".join(code.upper().split())
        grade = grade.strip().upper()
        if not separator or not code or grade not in GRADE_POINTS:
            raise ValueError(
                "Use one course and valid grade per line, like CSC 3102: B."
            )
        if code in grades:
            raise ValueError(f"Enter {code} only once.")
        grades[code] = grade
    return check_prerequisites(course_code, grades)


router: APIRouter = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home_page(
    request: Request, session: Session = Depends(require_login)
) -> RedirectResponse:
    """Open the dashboard from the site's root address.

    Args:
        request: Browser request for the site's root.
        session: The verified student; signed-out visitors go to login.

    Returns:
        An uncached redirect to the canonical dashboard URL.
    """
    return redirect_to("/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    course_code: str = "",
    completed: str = "",
    session: Session = Depends(require_login),
) -> HTMLResponse:
    """Display selected schedule, GPA forecast, and upcoming event sections.

    Args:
        request: Browser request for the dashboard.
        course_code: Optional course to check for prerequisites.
        completed: Completed courses, one COURSE: GRADE entry per line.
        session: The verified student whose data is shown.

    Returns:
        William's layout populated with actual supplied values or empty states.
    """
    data: DashboardData = dashboard_data(session)
    course_result: CourseResult | None = None
    course_error: str = ""
    if course_code or completed:
        try:
            course_result = check_courses(course_code, completed)
        except ValueError as error:
            course_error = str(error)
    return render_page(
        request,
        "tiger_dashboard.html",
        data=data,
        course_code=course_code,
        completed=completed,
        course_result=course_result,
        course_error=course_error,
        profile=tiger_auth.nav_profile(session),
        status_code=400 if course_error else 200,
    )


@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Open the schedule page; the page script loads schedules from the API.

    Args:
        request: Browser request for the schedule page.
        session: The verified student; signed-out visitors go to login.

    Returns:
        A schedule page with the current week's headings.
    """
    today: datetime = datetime.now(ZONE)
    week_start: datetime = today - timedelta(days=today.weekday())
    week_days: list[dict[str, str]] = []
    for index in range(7):
        day: datetime = week_start + timedelta(days=index)
        week_days.append(
            {"name": day.strftime("%A"), "date": day.strftime("%b %d")}
        )
    return render_page(
        request,
        "tiger_schedule.html",
        week_days=week_days,
        profile=tiger_auth.nav_profile(session),
    )


@router.get("/friends", response_class=HTMLResponse)
def friends_page(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Open the existing Friends interface with shared navigation.

    Args:
        request: Browser request for the Friends page.
        session: The verified student; signed-out visitors go to login.

    Returns:
        The Friends page and its existing schedule-sharing controls.
    """
    return render_page(
        request, "tiger_friends.html", profile=tiger_auth.nav_profile(session)
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Display only the verified student's account and saved profile data.

    Args:
        request: Browser request for the profile page.
        session: The verified student whose profile is shown.

    Returns:
        The student's profile page.
    """
    profile: AccountCard = tiger_auth.session_card(session)
    return render_page(
        request,
        "tiger_profile.html",
        profile=profile,
        saved=request.query_params.get("saved") == "1",
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
