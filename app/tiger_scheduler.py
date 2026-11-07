"""Schedule API and session-scoped schedule data operations."""
from copy import deepcopy
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request, Response, status

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

router = APIRouter(prefix="/api", tags=["Schedules"])
SESSION_COOKIE = "schedule_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
# Keep storage in these two helpers so the in-memory prototype can later use Supabase.
_session_data: dict[str, SchedulePageData] = {}

##Build data for testing and prototyping
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
    return Classes(
        id=event_id,
        title=title,
        department=department,
        number=number,
        grade=0.0,
        semester="Fall 2026",
        category="other",
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
    return Schedule(id=schedule_id, name=name, color=color, events=events)


def _user(user_id: int, username: str, schedules: list[Schedule]) -> UserBase:
    return UserBase(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        gpa=0,
        courses=[],
        schedules=schedules,
    )

##Build course from json data
def _course_presets() -> list[CoursePreset]:
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
                courseId=f"{department.lower()}-{number}-sample-section",
                title=course["course_code"],
                department=department,
                number=int(number),
                grade=0.0,
                semester="Spring Semester 2027",
                category=course["category"],
                professor="Sample instructor",
                enrollment="Sample enrollment",
                sectionDetails=f"Sample section | {day_labels} | {start}-{end}",
                days=days,
                start=start,
                end=end,
                location="",
                guests=[],
                favorite=False,
            ),
        )

    return presets

##Default data for testing and prototyping
def _default_data() -> SchedulePageData:
    user_schedules = [
        _schedule("fall_2026", "Fall 2026", "blue", [
            _class_event("csc-3380", "CSC 3380", "CSC", 3380,
                         ["Monday", "Wednesday", "Friday"], "09:00", "12:00",
                         "Geoscience Complex, E0137", ["User", "User"], True),
        ]),
        _schedule("work", "Work", "orange", [
            _event("library-shift", "Library Shift", ["Tuesday", "Thursday", "Saturday"], "11:00", "15:00"),
        ]),
        _schedule("clubs", "Clubs", "green", [
            _event("wics-officers", "WICS Officers", ["Monday"], "14:00", "17:00",
                   "PFT, 1263", ["User", "User"]),
        ]),
        _schedule("other", "Other", "purple", [
            _event("gym-workout", "Gym Workout", ["Tuesday"], "17:00", "19:00"),
        ]),
    ]

    users = [
        _user(0, "user", user_schedules),
        _user(1, "user1", [
            _schedule("user1-fall-2026", "Fall 2026", "yellow", [
                _class_event("user1-csc-3380", "CSC 3380", "CSC", 3380, ["Monday", "Wednesday", "Friday"], "09:00", "12:00", "PFT 1210"),
                _class_event("user1-csc-3304", "CSC 3304", "CSC", 3304, ["Monday", "Wednesday", "Friday"], "13:00", "15:00", "PFT 1200"),
                _event("user1-study-group", "Study Group", ["Tuesday"], "15:30", "17:00", "Library"),
            ]),
        ]),
        _user(2, "user2", [
            _schedule("user2-fall-2026", "Fall 2026", "yellow", [
                _class_event("user2-biol-1201", "BIOL 1201", "BIOL", 1201, ["Monday", "Wednesday", "Friday"], "10:00", "12:00", "Lockett Hall"),
                _event("user2-chem-lab", "Chemistry Lab", ["Tuesday", "Thursday"], "13:00", "16:00", "Chemistry Labs"),
            ]),
        ]),
        _user(3, "user3", [
            _schedule("user3-fall-2026", "Fall 2026", "yellow", [
                _class_event("user3-biol-1201", "BIOL 1201", "BIOL", 1201, ["Monday", "Wednesday", "Friday"], "09:00", "11:00", "Lockett Hall"),
                _event("user3-seminar", "Seminar", ["Tuesday", "Thursday"], "14:00", "16:00", "Life Sciences"),
            ]),
        ]),
        _user(4, "user4", [
            _schedule("user4-fall-2026", "Fall 2026", "yellow", [
                _class_event("user4-biol-1201", "BIOL 1201", "BIOL", 1201, ["Monday", "Wednesday", "Friday"], "10:00", "12:00", "Lockett Hall"),
                _event("user4-chem-lab", "Chemistry Lab", ["Tuesday", "Thursday"], "13:00", "16:00", "Chemistry Labs"),
            ]),
        ]),
        _user(5, "user5", [
            _schedule("user5-fall-2026", "Fall 2026", "yellow", [
                _class_event("user5-csc-3380", "CSC 3380", "CSC", 3380, ["Monday", "Wednesday", "Friday"], "09:00", "12:00", "Geoscience Complex"),
                _class_event("user5-csc-3304", "CSC 3304", "CSC", 3304, ["Monday", "Wednesday", "Friday"], "13:00", "15:00", "PFT"),
                _event("user5-study-group", "Study Group", ["Tuesday"], "15:30", "17:00", "Library"),
            ]),
        ]),
        _user(6, "user6", [
            _schedule("user6-fall-2026", "Fall 2026", "yellow", [
                _class_event("user6-biol-1201", "BIOL 1201", "BIOL", 1201, ["Monday", "Wednesday", "Friday"], "10:00", "12:00", "Lockett Hall"),
                _event("user6-chem-lab", "Chemistry Lab", ["Tuesday", "Thursday"], "13:00", "16:00", "Chemistry Labs"),
            ]),
        ]),
    ]
    return SchedulePageData(
        current_user_id=0,
        users=users,
        metrics={},
    )


_DEFAULT_DATA = _default_data()

#Gets the session data from the request and if it does not exist it will create a new session and return the default data.
def _get_session_data(request: Request, response: Response) -> SchedulePageData:
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

##Save data to session data by session id
def _save_session_data(request: Request, data: SchedulePageData) -> None:
    _session_data[request.state.schedule_session_id] = data

def _find_current_user(data: SchedulePageData) -> UserBase:
    user = next((item for item in data.users if item.id == data.current_user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="Current user not found.")
    return user


def _find_schedule(data: SchedulePageData, schedule_id: str) -> Schedule:
    schedule = next(
        (item for item in _find_current_user(data).schedules if item.id == schedule_id),
        None,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return schedule


def _find_event(schedule: Schedule, event_id: str) -> int:
    index = next((i for i, event in enumerate(schedule.events) if event.id == event_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return index

#Check for confliction schedule conflicts, raise error if so
def _ensure_no_schedule_conflicts(
    schedule: Schedule,
    proposed_event: ScheduleEventData,
    exclude_event_id: str | None = None,
) -> None:
    conflicting_names = [
        event.title
        for event in schedule.events
        if event.id != exclude_event_id
        and set(proposed_event.days).intersection(event.days)
        and proposed_event.start < event.end
        and event.start < proposed_event.end
    ]
    if conflicting_names:
        event_names = list(dict.fromkeys([proposed_event.title, *conflicting_names]))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "schedule_conflict",
                "event_names": event_names,
            },
        )


def calculate_schedule_metrics(schedule: Schedule) -> ScheduleMetrics:
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    busy_days = {day for event in schedule.events for day in event.days}
    total_minutes = sum(
        (
            int(event.end[:2]) * 60 + int(event.end[3:])
            - int(event.start[:2]) * 60 - int(event.start[3:])
        ) * len(event.days)
        for event in schedule.events
    )
    return ScheduleMetrics(
        totalHours=(total_minutes + 59) // 60,
        daysBusy=", ".join(day[:3] for day in weekdays if day in busy_days) or "—",
    )


def get_schedule_page_data(data: SchedulePageData) -> SchedulePageData:
    result = deepcopy(data)
    current_user = _find_current_user(result)
    result.metrics = {
        schedule.id: calculate_schedule_metrics(schedule)
        for schedule in current_user.schedules
    }
    return result


def _time_to_minutes(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def _minutes_to_time(value: int) -> str:
    return f"{value // 60:02}:{value % 60:02}"

#Calculates free time shared between two users between their two schedules given a time range and minimum duration, Returns a list of days with available free time periods
def calculate_shared_free_time(
    current_user: UserBase,
    friend: UserBase,
    start_time: str,
    end_time: str,
    minimum_duration: int,
) -> SharedFreeTimeResponse:
    range_start = _time_to_minutes(start_time)
    range_end = _time_to_minutes(end_time)
    events = [
        event
        for user in (current_user, friend)
        for schedule in user.schedules
        for event in schedule.events
    ]
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    available_days = []

    for day in weekdays:
        busy_intervals = sorted(
            (
                max(_time_to_minutes(event.start), range_start),
                min(_time_to_minutes(event.end), range_end),
            )
            for event in events
            if day in event.days
            and _time_to_minutes(event.end) > range_start
            and _time_to_minutes(event.start) < range_end
        )
        merged_intervals: list[tuple[int, int]] = []
        for interval_start, interval_end in busy_intervals:
            if merged_intervals and interval_start <= merged_intervals[-1][1]:
                previous_start, previous_end = merged_intervals[-1]
                merged_intervals[-1] = (previous_start, max(previous_end, interval_end))
            else:
                merged_intervals.append((interval_start, interval_end))

        periods: list[SharedFreeTimePeriod] = []
        cursor = range_start
        for interval_start, interval_end in merged_intervals:
            if interval_start - cursor >= minimum_duration:
                periods.append(
                    SharedFreeTimePeriod(
                        start=_minutes_to_time(cursor),
                        end=_minutes_to_time(interval_start),
                    ),
                )
            cursor = max(cursor, interval_end)
        if range_end - cursor >= minimum_duration:
            periods.append(
                SharedFreeTimePeriod(
                    start=_minutes_to_time(cursor),
                    end=_minutes_to_time(range_end),
                ),
            )
        if periods:
            available_days.append(SharedFreeTimeDay(day=day, periods=periods))

    return SharedFreeTimeResponse(days=available_days)


@router.get("/schedule-data", response_model=SchedulePageData)
def get_schedule_data(request: Request, response: Response) -> SchedulePageData:
    return get_schedule_page_data(_get_session_data(request, response))


@router.post("/shared-free-time", response_model=SharedFreeTimeResponse)
def get_shared_free_time(
    query: SharedFreeTimeRequest,
    request: Request,
    response: Response,
) -> SharedFreeTimeResponse:
    data = _get_session_data(request, response)
    current_user = _find_current_user(data)
    friend = next(
        (user for user in data.users if user.username == query.friend_username),
        None,
    )
    if friend is None or friend.id == current_user.id:
        raise HTTPException(status_code=404, detail="Friend not found.")

    return calculate_shared_free_time(
        current_user,
        friend,
        query.start_time,
        query.end_time,
        query.minimum_duration,
    )


@router.get("/course-presets", response_model=list[CoursePreset])
def search_course_presets(
    query: str = "",
) -> list[CoursePreset]:
    search_term = query.strip().casefold()
    return [
        course for course in _course_presets()
        if not search_term or search_term in " ".join(
            [
                course.title,
                course.semester,
                course.professor,
                course.section_details,
                course.category,
            ]
        ).casefold()
    ]


@router.post("/schedules", response_model=Schedule, status_code=status.HTTP_201_CREATED)
def create_schedule(
    definition: ScheduleDefinition,
    request: Request,
    response: Response,
) -> Schedule:
    data = _get_session_data(request, response)
    schedule = Schedule(**definition.model_dump(), events=[])
    _find_current_user(data).schedules.append(schedule)
    _save_session_data(request, data)
    return schedule


@router.put("/schedules/{schedule_id}", response_model=Schedule)
def update_schedule(
    schedule_id: str,
    definition: ScheduleDefinition,
    request: Request,
    response: Response,
) -> Schedule:
    data = _get_session_data(request, response)
    schedule = _find_schedule(data, schedule_id)
    schedule.name = definition.name
    schedule.color = definition.color
    _save_session_data(request, data)
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: str, request: Request, response: Response) -> Response:
    data = _get_session_data(request, response)
    schedules = _find_current_user(data).schedules
    if len(schedules) <= 1:
        raise HTTPException(status_code=409, detail="At least one schedule must remain.")
    schedule = _find_schedule(data, schedule_id)
    schedules.remove(schedule)
    _save_session_data(request, data)
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
    data = _get_session_data(request, response)
    schedule = _find_schedule(data, schedule_id)
    created = ScheduleEvent(**event.model_dump())
    _ensure_no_schedule_conflicts(schedule, created)
    schedule.events.append(created)
    _save_session_data(request, data)
    return created


@router.post(
    "/schedules/{schedule_id}/courses",
    response_model=Classes,
    status_code=status.HTTP_201_CREATED,
)
def add_course_to_schedule(
    schedule_id: str,
    selection: CourseSelection,
    request: Request,
    response: Response,
) -> Classes:
    data = _get_session_data(request, response)
    schedule = _find_schedule(data, schedule_id)
    course = next(
        (item for item in _course_presets() if item.course_id == selection.course_id),
        None,
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course section not found.")
    event = Classes(**course.model_dump(
        exclude={"id", "course_id", "professor", "enrollment", "section_details", "credit"},
    ))
    _ensure_no_schedule_conflicts(schedule, event)
    schedule.events.append(event)
    _save_session_data(request, data)
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
    data = _get_session_data(request, response)
    schedule = _find_schedule(data, schedule_id)
    event_index = _find_event(schedule, event_id)
    existing = schedule.events[event_index]
    updated = type(existing)(
        **{
            **existing.model_dump(exclude={"credit"}),
            **event.model_dump(),
            "id": event_id,
        },
    )
    _ensure_no_schedule_conflicts(schedule, updated, exclude_event_id=event_id)
    schedule.events[event_index] = updated
    _save_session_data(request, data)
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
    data = _get_session_data(request, response)
    schedule = _find_schedule(data, schedule_id)
    event_index = _find_event(schedule, event_id)
    del schedule.events[event_index]
    _save_session_data(request, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
