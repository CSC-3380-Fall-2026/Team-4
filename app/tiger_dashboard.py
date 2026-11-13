"""Provide dashboard display values through an explicit backend connection."""

from datetime import datetime, timezone
from typing import Callable, cast
from zoneinfo import ZoneInfo
from fastapi import Request

from models.tiger_dashboard import DashboardData, UpcomingEvent
from tiger_forecast import read_forecast


def dashboard_data(request: Request) -> DashboardData:
    """Read provided schedule data and this browser's last GPA forecast.

    Args:
        request: Browser request and the application's optional data provider.

    Returns:
        Typed summary values, with honest empty states when no provider exists.
    """
    provider = cast(
        Callable[[Request], DashboardData] | None,
        getattr(request.app.state, "dashboard_provider", None),
    )
    data: DashboardData = (
        provider(request).model_copy(deep=True) if provider else DashboardData()
    )
    now: datetime = datetime.now(timezone.utc)
    data.events = sorted(
        [event for event in data.events if event.starts_at >= now],
        key=event_time,
    )[:6]
    for event in data.events:
        event.starts_at = event.starts_at.astimezone(
            ZoneInfo("America/Chicago")
        )
    forecast = read_forecast(request)
    if forecast is not None:
        data.forecast = forecast
    return data


def event_time(event: UpcomingEvent) -> datetime:
    """Provide the timestamp used to order upcoming events.

    Args:
        event: An event supplied by the schedule backend.

    Returns:
        The timezone-aware event start time.
    """
    return event.starts_at
