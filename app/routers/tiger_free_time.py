"""Shared free time with a friend, and the per-schedule metrics on the Schedule page."""

from copy import deepcopy
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from models.tiger_free_time import (
    SharedFreeTimeDay,
    SharedFreeTimePeriod,
    SharedFreeTimeRequest,
    SharedFreeTimeResponse,
)
from models.tiger_schedules import (
    WEEKDAYS,
    Schedule,
    ScheduleMetrics,
    SchedulePageData,
    UserBase,
)
from models.tiger_session import Session
from routers.tiger_schedules_store import load_page
from tiger_auth import current_session


def find_user(data: SchedulePageData) -> UserBase:
    """Find the current user in the page data.

    Args:
        data: Page data to search.

    Returns:
        The current user.

    Raises:
        HTTPException: If the user does not exist.
    """
    user = next(
        (item for item in data.users if item.id == data.current_user_id),
        None,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Current user not found.")
    return user


def _to_minutes(value: str) -> int:
    """Convert an HH:MM string to minutes after midnight.

    Args:
        value: Time as HH:MM.

    Returns:
        Minutes after midnight.
    """
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def _to_time(value: int) -> str:
    """Convert minutes after midnight to an HH:MM string.

    Args:
        value: Minutes after midnight.

    Returns:
        Time as HH:MM.
    """
    return f"{value // 60:02}:{value % 60:02}"


def schedule_metrics(schedule: Schedule) -> ScheduleMetrics:
    """Compute total hours and busy days for a schedule.

    Args:
        schedule: Schedule to measure.

    Returns:
        The schedule's metrics.
    """
    busy_days = {
        day
        for event in schedule.events
        for day in event.days
    }

    total_minutes = sum(
        (_to_minutes(event.end) - _to_minutes(event.start)) * len(event.days)
        for event in schedule.events
    )

    return ScheduleMetrics(
        total_hours=(total_minutes + 59) // 60,
        days_busy=", ".join(
            day[:3] for day in WEEKDAYS if day in busy_days
        ) or "—",
    )


def page_data(data: SchedulePageData) -> SchedulePageData:
    """Return a copy of the page data with metrics filled in.

    Args:
        data: Page data to copy.

    Returns:
        Page data including per-schedule metrics.
    """
    result = deepcopy(data)
    current_user = find_user(result)

    result.metrics = {
        schedule.id: schedule_metrics(schedule)
        for schedule in current_user.schedules
    }

    return result


def free_time(
    schedules: list[Schedule],
    start_time: str,
    end_time: str,
    minimum_duration: int,
) -> SharedFreeTimeResponse:
    """Compute weekly free periods that no given schedule is busy in.

    Args:
        schedules: The student's chosen schedule and the friend's chosen one.
        start_time: Start of the search window as HH:MM.
        end_time: End of the search window as HH:MM.
        minimum_duration: Shortest free period in minutes.

    Returns:
        Days with their shared free periods.
    """
    range_start = _to_minutes(start_time)
    range_end = _to_minutes(end_time)

    events = [event for schedule in schedules for event in schedule.events]

    available_days = []

    for day in WEEKDAYS:
        busy_intervals = sorted(
            (
                max(_to_minutes(event.start), range_start),
                min(_to_minutes(event.end), range_end),
            )
            for event in events
            if day in event.days
            and _to_minutes(event.end) > range_start
            and _to_minutes(event.start) < range_end
        )

        merged_intervals: list[tuple[int, int]] = []

        for interval_start, interval_end in busy_intervals:
            if (
                merged_intervals
                and interval_start <= merged_intervals[-1][1]
            ):
                previous_start, previous_end = merged_intervals[-1]
                merged_intervals[-1] = (
                    previous_start,
                    max(previous_end, interval_end),
                )
            else:
                merged_intervals.append((interval_start, interval_end))

        periods: list[SharedFreeTimePeriod] = []
        cursor = range_start

        for interval_start, interval_end in merged_intervals:
            if interval_start - cursor >= minimum_duration:
                periods.append(
                    SharedFreeTimePeriod(
                        start=_to_time(cursor),
                        end=_to_time(interval_start),
                    ),
                )
            cursor = max(cursor, interval_end)

        if range_end - cursor >= minimum_duration:
            periods.append(
                SharedFreeTimePeriod(
                    start=_to_time(cursor),
                    end=_to_time(range_end),
                ),
            )

        if periods:
            available_days.append(
                SharedFreeTimeDay(day=day, periods=periods)
            )

    return SharedFreeTimeResponse(days=available_days)


def pick_schedule(schedules: list[Schedule], wanted: UUID | None) -> list[Schedule]:
    """Pick one schedule by id, or the first one when none is asked for.

    Args:
        schedules: The schedules to choose from.
        wanted: Id of the schedule to use, or None for the first.

    Returns:
        A list holding the chosen schedule, or empty when there are none.

    Raises:
        HTTPException: 404 when the wanted id is not among the schedules.
    """
    if wanted is None:
        return schedules[:1]
    chosen = [item for item in schedules if item.id == str(wanted)]
    if not chosen:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return chosen


router: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])


@router.post("/shared-free-time", response_model=SharedFreeTimeResponse)
def shared_free(
    query: SharedFreeTimeRequest,
    session: Session = Depends(current_session),
) -> SharedFreeTimeResponse:
    """Find free time shared by one of the student's schedules and a friend.

    Args:
        query: Friend id, the student's schedule, the friend's shared
            schedule, time window, and minimum duration.
        session: Verified student and their database client.

    Returns:
        Shared free periods by day.

    Raises:
        HTTPException: 404 when the friend has shared nothing with the
            student, the schedule is not the student's, or the friend's
            schedule is not one they shared with the student.
    """
    data = load_page(session)
    current_user = find_user(data)
    friend = next(
        (
            user
            for user in data.users
            if user.id == query.friend_id and user.id != current_user.id
        ),
        None,
    )
    if friend is None:
        raise HTTPException(status_code=404, detail="Friend not found.")
    mine = pick_schedule(current_user.schedules, query.schedule_id)
    theirs = pick_schedule(friend.schedules, query.friend_schedule_id)
    return free_time(
        [*mine, *theirs],
        query.start_time,
        query.end_time,
        query.minimum_duration,
    )
