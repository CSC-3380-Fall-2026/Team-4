"""Schedule APIs for saved records and the existing session-based page.

/api/saved-schedules stores schedules in Supabase for the signed-in account.
/api/schedules supports the existing prototype page and its in-memory events.
The prototype page still requires integration with the saved-schedule API.
"""

from copy import deepcopy
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

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
    ScheduleIn,
    ScheduleMetrics,
    ScheduleOut,
    SchedulePageData,
    SharedFreeTimeDay,
    SharedFreeTimePeriod,
    SharedFreeTimeRequest,
    SharedFreeTimeResponse,
    UserBase,
)

router: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])


# Supabase-backed operations use their own paths to avoid colliding with the page.
def _to_out(row: dict[str, Any]) -> ScheduleOut:
    """Convert a Supabase row into a ScheduleOut.

    Args:
        row: Raw schedule row from the database.

    Returns:
        The matching ScheduleOut model.
    """
    return ScheduleOut(
        id=row["id"],
        name=row["name"],
        semester=row["semester"],
        sections=row.get("sections") or [],
        commitments=row.get("commitments") or [],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _payload(schedule: ScheduleIn) -> dict[str, Any]:
    """Build the database payload for a saved schedule.

    Args:
        schedule: Incoming schedule data.

    Returns:
        Dict of columns to store.
    """
    return {
        "name": schedule.name,
        "semester": schedule.semester,
        "sections": [s.model_dump() for s in schedule.sections],
        "commitments": [c.model_dump() for c in schedule.commitments],
    }


@router.post("/saved-schedules")
def create_saved(schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    """Save a new schedule for the signed-in account.

    Args:
        schedule: Schedule data to store.
        session: Current authenticated session.

    Returns:
        The stored schedule.
    """
    row = {**_payload(schedule), "user_id": session.user_id}
    data = session.db.table("schedules").insert(row).execute().data
    if not data:
        raise HTTPException(status_code=400, detail="Could not save schedule")
    return _to_out(data[0])


@router.get("/saved-schedules")
def list_saved(session: Session = Depends(current_session)) -> list[ScheduleOut]:
    """List the signed-in account's saved schedules, newest first.

    Args:
        session: Current authenticated session.

    Returns:
        The saved schedules.
    """
    data = (
        session.db.table("schedules").select("*")
        .eq("user_id", session.user_id).order("updated_at", desc=True)
        .execute().data
    )
    return [_to_out(r) for r in (data or [])]


@router.get("/saved-schedules/{schedule_id}")
def get_saved(schedule_id: str, session: Session = Depends(current_session)) -> ScheduleOut:
    """Fetch one saved schedule.

    Args:
        schedule_id: ID of the schedule.
        session: Current authenticated session.

    Returns:
        The requested schedule.
    """
    data = (
        session.db.table("schedules").select("*")
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(data[0])


@router.put("/saved-schedules/{schedule_id}")
def update_saved(schedule_id: str, schedule: ScheduleIn, session: Session = Depends(current_session)) -> ScheduleOut:
    """Update one saved schedule.

    Args:
        schedule_id: ID of the schedule.
        schedule: New schedule data.
        session: Current authenticated session.

    Returns:
        The updated schedule.
    """
    changes = {**_payload(schedule), "updated_at": datetime.now(timezone.utc).isoformat()}
    data = (
        session.db.table("schedules").update(changes)
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(data[0])


@router.delete("/saved-schedules/{schedule_id}")
def delete_saved(schedule_id: str, session: Session = Depends(current_session)) -> dict[str, bool]:
    """Delete one saved schedule.

    Args:
        schedule_id: ID of the schedule.
        session: Current authenticated session.

    Returns:
        A dict confirming deletion.
    """
    data = (
        session.db.table("schedules").delete()
        .eq("id", schedule_id).eq("user_id", session.user_id).execute().data
    )
    if not data:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"deleted": True}


# Existing prototype page operations.
SESSION_COOKIE = "schedule_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30

# Prototype storage only: this is not shared across Vercel instances or restarts.
_session_data: dict[str, SchedulePageData] = {}


# Build data for testing and prototyping.
def _event(
    event_id: str,
    title: str,
    days: list[str],
    start: str,
    end: str,
    location: str = "",
    guests: list[str] | None = None,
    favorite: bool = False,
) -> ScheduleEvent:
    """Build a ScheduleEvent from plain values.

    Args:
        event_id: Unique event ID.
        title: Event title.
        days: Weekdays the event occurs.
        start: Start time as HH:MM.
        end: End time as HH:MM.
        location: Event location.
        guests: Guest names.
        favorite: Whether the event is favorited.

    Returns:
        The new ScheduleEvent.
    """
    return ScheduleEvent(
        id=event_id,
        title=title,
        days=days,
        start=start,
        end=end,
        location=location,
        guests=guests or [],
        favorite=favorite,
    )


def _class_event(
    event_id: str,
    title: str,
    department: str,
    number: int,
    days: list[str],
    start: str,
    end: str,
    location: str = "",
    guests: list[str] | None = None,
    favorite: bool = False,
) -> Classes:
    """Build a Classes entry with sample defaults.

    Args:
        event_id: Unique event ID.
        title: Class title.
        department: Department code.
        number: Course number.
        days: Weekdays the class meets.
        start: Start time as HH:MM.
        end: End time as HH:MM.
        location: Class location.
        guests: Guest names.
        favorite: Whether the class is favorited.

    Returns:
        The new Classes entry.
    """
    return Classes(
        id=event_id,
        title=title,
        department=department,
        number=number,
        grade=0.0,
        semester="Fall 2026",
        category="other",
        credit=3,
        days=days,
        start=start,
        end=end,
        location=location,
        guests=guests or [],
        favorite=favorite,
    )


def _schedule(
    schedule_id: str,
    name: str,
    color: str,
    events: list[Classes | ScheduleEvent],
) -> Schedule:
    """Build a Schedule from plain values.

    Args:
        schedule_id: Unique schedule ID.
        name: Schedule name.
        color: Schedule color.
        events: Events in the schedule.

    Returns:
        The new Schedule.
    """
    return Schedule(
        id=schedule_id,
        name=name,
        color=color,
        events=events,
    )


def _user(user_id: int, username: str, schedules: list[Schedule]) -> UserBase:
    """Build a sample user.

    Args:
        user_id: Numeric user ID.
        username: Username, also used for the email.
        schedules: The user's schedules.

    Returns:
        The new UserBase.
    """
    return UserBase(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        gpa=0,
        courses=[],
        schedules=schedules,
    )


# Build sample course sections from catalog data.
def _course_presets() -> list[CoursePreset]:
    """Build sample course sections from catalog data.

    Returns:
        The generated course presets.
    """
    presets = []
    day_patterns = [
        ["Monday", "Wednesday", "Friday"],
        ["Tuesday", "Thursday"],
    ]
    start_hours = [8, 9, 10, 13, 14, 15]

    for index, course in enumerate(load_courses()):
        department, number = course["course_code"].split()
        start_hour = start_hours[index % len(start_hours)]
        duration = course["credits"]
        end_hour = start_hour + duration
        days = day_patterns[index % len(day_patterns)]
        start = f"{start_hour:02}:00"
        end = f"{end_hour:02}:00"
        day_labels = ", ".join(day[:2] for day in days)

        presets.append(
            CoursePreset(
                course_id=f"{department.lower()}-{number}-sample-section",
                title=course["course_code"],
                department=department,
                number=int(number),
                grade=0.0,
                credit=course["credits"],
                semester="Spring Semester 2027",
                category=course["category"],
                professor="Sample instructor",
                enrollment="Sample enrollment",
                section_details=f"Sample section | {day_labels} | {start}-{end}",
                days=days,
                start=start,
                end=end,
                location="",
                guests=[],
                favorite=False,
            ),
        )

    return presets


# Default data for testing and prototyping.
def _default_data() -> SchedulePageData:
    """Build the default prototype page data.

    Returns:
        Sample SchedulePageData with several users.
    """
    user_schedules = [
        _schedule("fall_2026", "Fall 2026", "blue", [
            _class_event(
                "csc-3380",
                "CSC 3380",
                "CSC",
                3380,
                ["Monday", "Wednesday", "Friday"],
                "09:00",
                "12:00",
                "Geoscience Complex, E0137",
                ["User", "User"],
                True,
            ),
        ]),
        _schedule("work", "Work", "orange", [
            _event(
                "library-shift",
                "Library Shift",
                ["Tuesday", "Thursday", "Saturday"],
                "11:00",
                "15:00",
            ),
        ]),
        _schedule("clubs", "Clubs", "green", [
            _event(
                "wics-officers",
                "WICS Officers",
                ["Monday"],
                "14:00",
                "17:00",
                "PFT, 1263",
                ["User", "User"],
            ),
        ]),
        _schedule("other", "Other", "purple", [
            _event(
                "gym-workout",
                "Gym Workout",
                ["Tuesday"],
                "17:00",
                "19:00",
            ),
        ]),
    ]

    users = [
        _user(0, "user", user_schedules),
        _user(1, "user1", [
            _schedule("user1-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user1-csc-3380",
                    "CSC 3380",
                    "CSC",
                    3380,
                    ["Monday", "Wednesday", "Friday"],
                    "09:00",
                    "12:00",
                    "PFT 1210",
                ),
                _class_event(
                    "user1-csc-3304",
                    "CSC 3304",
                    "CSC",
                    3304,
                    ["Monday", "Wednesday", "Friday"],
                    "13:00",
                    "15:00",
                    "PFT 1200",
                ),
                _event(
                    "user1-study-group",
                    "Study Group",
                    ["Tuesday"],
                    "15:30",
                    "17:00",
                    "Library",
                ),
            ]),
        ]),
        _user(2, "user2", [
            _schedule("user2-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user2-biol-1201",
                    "BIOL 1201",
                    "BIOL",
                    1201,
                    ["Monday", "Wednesday", "Friday"],
                    "10:00",
                    "12:00",
                    "Lockett Hall",
                ),
                _event(
                    "user2-chem-lab",
                    "Chemistry Lab",
                    ["Tuesday", "Thursday"],
                    "13:00",
                    "16:00",
                    "Chemistry Labs",
                ),
            ]),
        ]),
        _user(3, "user3", [
            _schedule("user3-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user3-biol-1201",
                    "BIOL 1201",
                    "BIOL",
                    1201,
                    ["Monday", "Wednesday", "Friday"],
                    "09:00",
                    "11:00",
                    "Lockett Hall",
                ),
                _event(
                    "user3-seminar",
                    "Seminar",
                    ["Tuesday", "Thursday"],
                    "14:00",
                    "16:00",
                    "Life Sciences",
                ),
            ]),
        ]),
        _user(4, "user4", [
            _schedule("user4-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user4-biol-1201",
                    "BIOL 1201",
                    "BIOL",
                    1201,
                    ["Monday", "Wednesday", "Friday"],
                    "10:00",
                    "12:00",
                    "Lockett Hall",
                ),
                _event(
                    "user4-chem-lab",
                    "Chemistry Lab",
                    ["Tuesday", "Thursday"],
                    "13:00",
                    "16:00",
                    "Chemistry Labs",
                ),
            ]),
        ]),
        _user(5, "user5", [
            _schedule("user5-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user5-csc-3380",
                    "CSC 3380",
                    "CSC",
                    3380,
                    ["Monday", "Wednesday", "Friday"],
                    "09:00",
                    "12:00",
                    "Geoscience Complex",
                ),
                _class_event(
                    "user5-csc-3304",
                    "CSC 3304",
                    "CSC",
                    3304,
                    ["Monday", "Wednesday", "Friday"],
                    "13:00",
                    "15:00",
                    "PFT",
                ),
                _event(
                    "user5-study-group",
                    "Study Group",
                    ["Tuesday"],
                    "15:30",
                    "17:00",
                    "Library",
                ),
            ]),
        ]),
        _user(6, "user6", [
            _schedule("user6-fall-2026", "Fall 2026", "yellow", [
                _class_event(
                    "user6-biol-1201",
                    "BIOL 1201",
                    "BIOL",
                    1201,
                    ["Monday", "Wednesday", "Friday"],
                    "10:00",
                    "12:00",
                    "Lockett Hall",
                ),
                _event(
                    "user6-chem-lab",
                    "Chemistry Lab",
                    ["Tuesday", "Thursday"],
                    "13:00",
                    "16:00",
                    "Chemistry Labs",
                ),
            ]),
        ]),
    ]

    return SchedulePageData(
        current_user_id=0,
        users=users,
        metrics={},
    )


_DEFAULT_DATA = _default_data()


# Get or create the prototype session data.
def _load_session(request: Request, response: Response) -> SchedulePageData:
    """Get or create the prototype data for the request's session.

    Args:
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The session's SchedulePageData.
    """
    session_id = request.cookies.get(SESSION_COOKIE)

    if not session_id:
        session_id = token_urlsafe(32)
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )

    request.state.schedule_session_id = session_id

    if session_id not in _session_data:
        _session_data[session_id] = deepcopy(_DEFAULT_DATA)

    return _session_data[session_id]


def _save_session(request: Request, data: SchedulePageData) -> None:
    """Store the prototype data for the request's session.

    Args:
        request: Incoming request carrying the session ID.
        data: Page data to store.
    """
    _session_data[request.state.schedule_session_id] = data


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


def _find_schedule(data: SchedulePageData, schedule_id: str) -> Schedule:
    """Find a schedule belonging to the current user.

    Args:
        data: Page data to search.
        schedule_id: ID of the schedule.

    Returns:
        The matching schedule.

    Raises:
        HTTPException: If the schedule does not exist.
    """
    schedule = next(
        (
            item
            for item in _find_user(data).schedules
            if item.id == schedule_id
        ),
        None,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return schedule


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
        totalHours=(total_minutes + 59) // 60,
        daysBusy=", ".join(
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

    weekdays = [
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
def schedule_data(request: Request, response: Response) -> SchedulePageData:
    """Return the prototype page data for the session.

    Args:
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        Page data with metrics.
    """
    return page_data(
        _load_session(request, response)
    )


@router.post("/shared-free-time", response_model=SharedFreeTimeResponse)
def shared_free(
    query: SharedFreeTimeRequest,
    request: Request,
    response: Response,
) -> SharedFreeTimeResponse:
    """Find free time shared with a friend.

    Args:
        query: Friend username, time window, and minimum duration.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        Shared free periods by day.
    """
    data = _load_session(request, response)
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
def search_presets(query: str = "") -> list[CoursePreset]:
    """Search the sample course sections.

    Args:
        query: Text to match, or empty for all.

    Returns:
        Matching course presets.
    """
    search_term = query.strip().casefold()

    return [
        course
        for course in _course_presets()
        if not search_term
        or search_term in " ".join(
            [
                course.title,
                course.semester,
                course.professor,
                course.section_details,
                course.category,
            ]
        ).casefold()
    ]


@router.post(
    "/schedules",
    response_model=Schedule,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    definition: ScheduleDefinition,
    request: Request,
    response: Response,
) -> Schedule:
    """Create an empty schedule for the current user.

    Args:
        definition: Name and color for the schedule.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The new schedule.
    """
    data = _load_session(request, response)
    schedule = Schedule(**definition.model_dump(), events=[])

    _find_user(data).schedules.append(schedule)
    _save_session(request, data)

    return schedule


@router.put("/schedules/{schedule_id}", response_model=Schedule)
def update_schedule(
    schedule_id: str,
    definition: ScheduleDefinition,
    request: Request,
    response: Response,
) -> Schedule:
    """Rename or recolor a schedule.

    Args:
        schedule_id: ID of the schedule.
        definition: New name and color.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The updated schedule.
    """
    data = _load_session(request, response)
    schedule = _find_schedule(data, schedule_id)

    schedule.name = definition.name
    schedule.color = definition.color
    _save_session(request, data)

    return schedule


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_schedule(
    schedule_id: str,
    request: Request,
    response: Response,
) -> Response:
    """Delete a schedule, keeping at least one.

    Args:
        schedule_id: ID of the schedule.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        An empty 204 response.
    """
    data = _load_session(request, response)
    schedules = _find_user(data).schedules

    if len(schedules) <= 1:
        raise HTTPException(
            status_code=409,
            detail="At least one schedule must remain.",
        )

    schedule = _find_schedule(data, schedule_id)
    schedules.remove(schedule)
    _save_session(request, data)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/events",
    response_model=ScheduleEvent,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    schedule_id: str,
    event: ScheduleEventData,
    request: Request,
    response: Response,
) -> ScheduleEvent:
    """Add an event to a schedule.

    Args:
        schedule_id: ID of the schedule.
        event: Event data.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The created event.
    """
    data = _load_session(request, response)
    schedule = _find_schedule(data, schedule_id)
    created = ScheduleEvent(**event.model_dump())

    _check_conflicts(schedule, created)

    schedule.events.append(created)
    _save_session(request, data)

    return created


@router.post(
    "/schedules/{schedule_id}/courses",
    response_model=Classes,
    status_code=status.HTTP_201_CREATED,
)
def add_course(
    schedule_id: str,
    selection: CourseSelection,
    request: Request,
    response: Response,
) -> Classes:
    """Add a sample course section to a schedule.

    Args:
        schedule_id: ID of the schedule.
        selection: The chosen course section.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The created class entry.
    """
    data = _load_session(request, response)
    schedule = _find_schedule(data, schedule_id)

    course = next(
        (
            item
            for item in _course_presets()
            if item.course_id == selection.course_id
        ),
        None,
    )

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course section not found.",
        )

    event = Classes(
        **course.model_dump(
            exclude={
                "id",
                "course_id",
                "professor",
                "enrollment",
                "section_details",
            },
        )
    )

    _check_conflicts(schedule, event)

    schedule.events.append(event)
    _save_session(request, data)

    return event


@router.put(
    "/schedules/{schedule_id}/events/{event_id}",
    response_model=Classes | ScheduleEvent,
)
def update_event(
    schedule_id: str,
    event_id: str,
    event: ScheduleEventData,
    request: Request,
    response: Response,
) -> Classes | ScheduleEvent:
    """Update an event in a schedule.

    Args:
        schedule_id: ID of the schedule.
        event_id: ID of the event.
        event: New event data.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        The updated event.
    """
    data = _load_session(request, response)
    schedule = _find_schedule(data, schedule_id)
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
    _save_session(request, data)

    return updated


@router.delete(
    "/schedules/{schedule_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
    schedule_id: str,
    event_id: str,
    request: Request,
    response: Response,
) -> Response:
    """Delete an event from a schedule.

    Args:
        schedule_id: ID of the schedule.
        event_id: ID of the event.
        request: Incoming request.
        response: Response used to set the session cookie.

    Returns:
        An empty 204 response.
    """
    data = _load_session(request, response)
    schedule = _find_schedule(data, schedule_id)
    event_index = _find_event(schedule, event_id)

    del schedule.events[event_index]
    _save_session(request, data)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
