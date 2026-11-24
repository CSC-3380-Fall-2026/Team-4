"""Schedule page and JSON API, and the scheduling logic behind it."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from models.tiger_schedules import (
    Classes,
    CoursePreset,
    CourseSelection,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
    ScheduleEventData,
    SchedulePageData,
)
from models.tiger_session import Session
from routers import tiger_catalog, tiger_profiles
from routers.tiger_dashboard import ZONE
from routers.tiger_free_time import page_data
from routers.tiger_schedules_store import (
    current_semester,
    fetch_schedule,
    insert_schedule,
    list_schedules,
    load_page,
    remove_schedule,
    save_schedule,
)
from tiger_auth import current_session, require_login
from tiger_views import render_page

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


def course_presets() -> list[CoursePreset]:
    """Build course presets from the course catalog.

    Returns:
        One preset per catalog course.
    """
    return [preset_for(course) for course in tiger_catalog.load_courses()]


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
        (item for item in course_presets() if item.course_id == course_id),
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


def find_event(schedule: Schedule, event_id: str) -> int:
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


def check_conflicts(
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


router: APIRouter = APIRouter()


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
        profile=tiger_profiles.nav_profile(session),
    )


api: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])


@api.get("/schedule-data", response_model=SchedulePageData)
def schedule_data(session: Session = Depends(current_session)) -> SchedulePageData:
    """Return the student's page data with metrics.

    Args:
        session: Verified student and their database client.

    Returns:
        The student, friends' shared schedules, and metrics.
    """
    return page_data(load_page(session))


@api.get("/course-presets", response_model=list[CoursePreset])
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
        for course in course_presets()
        if not search_term
        or search_term in " ".join(
            [course.title, course.course_name, course.category]
        ).casefold()
    ]


@api.post(
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


@api.put("/schedules/{schedule_id}", response_model=Schedule)
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


@api.delete(
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

    Raises:
        HTTPException: 409 when it is the student's last schedule, or 404
            when it does not exist.
    """
    if len(list_schedules(session)) <= 1:
        raise HTTPException(
            status_code=409,
            detail="At least one schedule must remain.",
        )

    remove_schedule(session, schedule_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api.post(
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

    check_conflicts(schedule, created)

    schedule.events.append(created)
    save_schedule(session, schedule)

    return created


@api.post(
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

    check_conflicts(schedule, event)

    schedule.events.append(event)
    save_schedule(session, schedule)

    return event


@api.put(
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
    event_index = find_event(schedule, event_id)
    existing = schedule.events[event_index]

    updated = type(existing)(
        **{
            **existing.model_dump(),
            **event.model_dump(),
            "id": event_id,
        },
    )

    check_conflicts(
        schedule,
        updated,
        skip_id=event_id,
    )

    schedule.events[event_index] = updated
    save_schedule(session, schedule)

    return updated


@api.delete(
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
    event_index = find_event(schedule, event_id)

    del schedule.events[event_index]
    save_schedule(session, schedule)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# The page sits at the site root; the JSON routes above sit under /api.
router.include_router(api)
