"""Build dashboard display values from the student's saved Supabase data."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from models.tiger_dashboard import (
    DashboardData,
    ScheduleSummary,
    UpcomingEvent,
)
from models.tiger_session import Session
from tiger_auth import session_profile
from tiger_forecast import read_forecast
from models.tiger_schedules import WEEKDAYS, Classes, Schedule, ScheduleEvent
from routers.tiger_schedules_store import current_semester, list_schedules

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
