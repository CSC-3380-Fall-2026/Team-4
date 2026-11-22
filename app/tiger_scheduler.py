"""Schedule page APIs backed by each signed-in student's Supabase data."""

from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, Response, status

from tiger_auth import Session, current_session
from tiger_catalog import load_courses
from tiger_models import (
    Classes,
    CoursePreset,
    CourseSelection,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
    ScheduleEventData,
    ScheduleMetrics,
    SchedulePageData,
    SharedFreeTimeDay,
    SharedFreeTimePeriod,
    SharedFreeTimeRequest,
    SharedFreeTimeResponse,
    UserBase,
)
from tiger_schedule_store import (
    current_semester,
    fetch_schedule,
    insert_schedule,
    list_schedules,
    load_page,
    remove_schedule,
    save_schedule,
)

router: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])
DEFAULT_GRADE: float = 0.0


def preset_for(course: dict) -> CoursePreset:
    """Build a preset from one real catalog course.

    Args:
        course: Validated catalog course.

    Returns:
        The preset holding only catalog fields.
    """
    department, number = course["course_code"].split()
    return CoursePreset(
        course_id=course["course_code"],
        title=course["course_code"],
        course_name=course["course_name"],
        department=department,
        number=int(number),
        credit=course["credits"],
        category=course["category"],
        semester=current_semester(),
    )


def _course_presets() -> list[CoursePreset]:
    """Build course presets from the course catalog.

    Returns:
        One preset per catalog course.
    """
    return [preset_for(course) for course in load_courses()]


def _find_user(data: SchedulePageData) -> UserBase:
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



def _find_event(schedule: Schedule, event_id: str) -> int:
    """Find an event's index within a schedule.

    Args:
        schedule: Schedule to search.
        event_id: ID of the event.

    Returns:
        The event's list index.

    Raises:
        HTTPException: If the event does not exist.
    """
    index = next(
        (
            i
            for i, event in enumerate(schedule.events)
            if event.id == event_id
        ),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return index


def _check_conflicts(
    schedule: Schedule,
    proposed_event: ScheduleEventData,
    skip_id: str | None = None,
) -> None:
    """Reject an event that overlaps one already in the schedule.

    Args:
        schedule: Schedule to check against.
        proposed_event: Event being added or changed.
        skip_id: Event ID to ignore, if any.

    Raises:
        HTTPException: With status 409 on a time conflict.
    """
    conflicting_names = [
        event.title
        for event in schedule.events
        if event.id != skip_id
        and set(proposed_event.days).intersection(event.days)
        and proposed_event.start < event.end
        and event.start < proposed_event.end
    ]

    if conflicting_names:
        event_names = list(
            dict.fromkeys([proposed_event.title, *conflicting_names])
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "schedule_conflict",
                "event_names": event_names,
            },
        )


def schedule_metrics(schedule: Schedule) -> ScheduleMetrics:
    """Compute total hours and busy days for a schedule.

    Args:
        schedule: Schedule to measure.

    Returns:
        The schedule's metrics.
    """
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    busy_days = {
        day
        for event in schedule.events
        for day in event.days
    }

    total_minutes = sum(
        (
            int(event.end[:2]) * 60
            + int(event.end[3:])
            - int(event.start[:2]) * 60
            - int(event.start[3:])
        ) * len(event.days)
        for event in schedule.events
    )

    return ScheduleMetrics(
        total_hours=(total_minutes + 59) // 60,
        days_busy=", ".join(
            day[:3] for day in weekdays if day in busy_days
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
    current_user = _find_user(result)

    result.metrics = {
        schedule.id: schedule_metrics(schedule)
        for schedule in current_user.schedules
    }

    return result


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


def free_time(
    current_user: UserBase,
    friend: UserBase,
    start_time: str,
    end_time: str,
    minimum_duration: int,
) -> SharedFreeTimeResponse:
    """Compute weekly free periods shared by two users.

    Args:
        current_user: The signed-in user.
        friend: The friend to compare against.
        start_time: Start of the search window as HH:MM.
        end_time: End of the search window as HH:MM.
        minimum_duration: Shortest free period in minutes.

    Returns:
        Days with their shared free periods.
    """
    range_start = _to_minutes(start_time)
    range_end = _to_minutes(end_time)

    events = [
        event
        for user in (current_user, friend)
        for schedule in user.schedules
        for event in schedule.events
    ]

    weekdays: list[Weekday] = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    available_days = []

    for day in weekdays:
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


@router.get("/schedule-data", response_model=SchedulePageData)
def schedule_data(session: Session = Depends(current_session)) -> SchedulePageData:
    """Return the student's page data with metrics.

    Args:
        session: Verified student and their database client.

    Returns:
        The student, friends' shared schedules, and metrics.
    """
    return page_data(load_page(session))


@router.post("/shared-free-time", response_model=SharedFreeTimeResponse)
def shared_free(
    query: SharedFreeTimeRequest,
    session: Session = Depends(current_session),
) -> SharedFreeTimeResponse:
    """Find free time shared with a friend.

    Args:
        query: Friend username, time window, and minimum duration.
        session: Verified student and their database client.

    Returns:
        Shared free periods by day.
    """
    data = load_page(session)
    current_user = _find_user(data)

    friend = next(
        (
            user
            for user in data.users
            if user.username == query.friend_username
        ),
        None,
    )

    if friend is None or friend.id == current_user.id:
        raise HTTPException(status_code=404, detail="Friend not found.")

    return free_time(
        current_user,
        friend,
        query.start_time,
        query.end_time,
        query.minimum_duration,
    )


@router.get("/course-presets", response_model=list[CoursePreset])
def search_presets(
    query: str = "",
    session: Session = Depends(current_session),
) -> list[CoursePreset]:
    """Search the catalog courses.

    Args:
        query: Text to match, or empty for all.
        session: Verified student.

    Returns:
        Matching course presets.
    """
    search_term = query.strip().casefold()

    return [
        course
        for course in _course_presets()
        if not search_term
        or search_term in " ".join(
            [course.title, course.course_name, course.category]
        ).casefold()
    ]


def check_name(session: Session, name: str, skip_id: str | None = None) -> None:
    """Refuse a schedule name the student already uses.

    Args:
        session: Verified student and their database client.
        name: Proposed schedule name.
        skip_id: Schedule being renamed, which may keep its own name.

    Raises:
        HTTPException: 409 when another of the student's schedules has
            the same name, ignoring case.
    """
    wanted = name.strip().lower()
    for schedule in list_schedules(session):
        if schedule.id != skip_id and schedule.name.strip().lower() == wanted:
            raise HTTPException(
                status_code=409,
                detail=f'You already have a schedule named "{schedule.name}".',
            )


@router.post(
    "/schedules",
    response_model=Schedule,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    definition: ScheduleDefinition,
    session: Session = Depends(current_session),
) -> Schedule:
    """Create an empty schedule for the current student.

    Args:
        definition: Name and color for the schedule.
        session: Verified student and their database client.

    Returns:
        The new schedule.
    """
    check_name(session, definition.name)
    return insert_schedule(session, definition)


@router.put("/schedules/{schedule_id}", response_model=Schedule)
def update_schedule(
    schedule_id: str,
    definition: ScheduleDefinition,
    session: Session = Depends(current_session),
) -> Schedule:
    """Rename or recolor a schedule.

    Args:
        schedule_id: ID of the schedule.
        definition: New name and color.
        session: Verified student and their database client.

    Returns:
        The updated schedule.
    """
    schedule = fetch_schedule(session, schedule_id)
    check_name(session, definition.name, schedule_id)

    schedule.name = definition.name
    schedule.color = definition.color
    save_schedule(session, schedule)

    return schedule


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_schedule(
    schedule_id: str,
    session: Session = Depends(current_session),
) -> Response:
    """Delete a schedule, keeping at least one.

    Args:
        schedule_id: ID of the schedule.
        session: Verified student and their database client.

    Returns:
        An empty 204 response.
    """
    if len(list_schedules(session)) <= 1:
        raise HTTPException(
            status_code=409,
            detail="At least one schedule must remain.",
        )

    remove_schedule(session, schedule_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/events",
    response_model=ScheduleEvent,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    schedule_id: str,
    event: ScheduleEventData,
    session: Session = Depends(current_session),
) -> ScheduleEvent:
    """Add an event to a schedule.

    Args:
        schedule_id: ID of the schedule.
        event: Event data.
        session: Verified student and their database client.

    Returns:
        The created event.
    """
    schedule = fetch_schedule(session, schedule_id)
    created = ScheduleEvent(**event.model_dump())

    _check_conflicts(schedule, created)

    schedule.events.append(created)
    save_schedule(session, schedule)

    return created


def find_preset(course_id: str) -> CoursePreset:
    """Look up a catalog course by id.

    Args:
        course_id: Course code used as the preset id.

    Returns:
        The matching preset.

    Raises:
        HTTPException: With status 404 when the course is unknown.
    """
    course = next(
        (item for item in _course_presets() if item.course_id == course_id),
        None,
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def class_event(course: CoursePreset, selection: CourseSelection) -> Classes:
    """Combine a catalog course with the student's chosen meeting times.

    Args:
        course: Catalog course being added.
        selection: Meeting days, times and notes chosen by the student.

    Returns:
        The class event.
    """
    meeting = selection.model_dump(exclude={"course_id", "title"})
    return Classes(
        title=course.title,
        department=course.department,
        number=course.number,
        grade=DEFAULT_GRADE,
        semester=course.semester,
        category=course.category,
        credit=course.credit,
        **meeting,
    )


@router.post(
    "/schedules/{schedule_id}/courses",
    response_model=Classes,
    status_code=status.HTTP_201_CREATED,
)
def add_course(
    schedule_id: str,
    selection: CourseSelection,
    session: Session = Depends(current_session),
) -> Classes:
    """Add a catalog course, with the chosen meeting times, to a schedule.

    Args:
        schedule_id: ID of the schedule.
        selection: The chosen course and its meeting times.
        session: Verified student and their database client.

    Returns:
        The created class entry.
    """
    schedule = fetch_schedule(session, schedule_id)
    event = class_event(find_preset(selection.course_id), selection)

    _check_conflicts(schedule, event)

    schedule.events.append(event)
    save_schedule(session, schedule)

    return event


@router.put(
    "/schedules/{schedule_id}/events/{event_id}",
    response_model=Classes | ScheduleEvent,
)
def update_event(
    schedule_id: str,
    event_id: str,
    event: ScheduleEventData,
    session: Session = Depends(current_session),
) -> Classes | ScheduleEvent:
    """Update an event in a schedule.

    Args:
        schedule_id: ID of the schedule.
        event_id: ID of the event.
        event: New event data.
        session: Verified student and their database client.

    Returns:
        The updated event.
    """
    schedule = fetch_schedule(session, schedule_id)
    event_index = _find_event(schedule, event_id)
    existing = schedule.events[event_index]

    updated = type(existing)(
        **{
            **existing.model_dump(),
            **event.model_dump(),
            "id": event_id,
        },
    )

    _check_conflicts(
        schedule,
        updated,
        skip_id=event_id,
    )

    schedule.events[event_index] = updated
    save_schedule(session, schedule)

    return updated


@router.delete(
    "/schedules/{schedule_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
    schedule_id: str,
    event_id: str,
    session: Session = Depends(current_session),
) -> Response:
    """Delete an event from a schedule.

    Args:
        schedule_id: ID of the schedule.
        event_id: ID of the event.
        session: Verified student and their database client.

    Returns:
        An empty 204 response.
    """
    schedule = fetch_schedule(session, schedule_id)
    event_index = _find_event(schedule, event_id)

    del schedule.events[event_index]
    save_schedule(session, schedule)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
