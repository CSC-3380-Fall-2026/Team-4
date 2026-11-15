"""Typed values supplied to the dashboard and schedule templates."""

from pydantic import AwareDatetime, BaseModel, Field

from models.tiger_planning import PlanningResult


class ScheduleSummary(BaseModel):
    """A verified student's selected schedule, supplied by the schedule backend."""

    name: str
    semester: str = ""
    credit_hours: int = Field(default=0, ge=0)
    course_count: int = Field(default=0, ge=0)


class UpcomingEvent(BaseModel):
    """An event supplied by the current student's schedule backend."""

    title: str
    starts_at: AwareDatetime
    location: str = ""


class DashboardData(BaseModel):
    """Display data; absent records remain empty instead of becoming sample data."""

    selected: ScheduleSummary | None = None
    forecast: PlanningResult | None = None
    events: list[UpcomingEvent] = Field(default_factory=list)
