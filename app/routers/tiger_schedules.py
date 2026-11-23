"""Schedule page JSON API backed by each signed-in student's Supabase data."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from models.tiger_schedule import (
    Classes,
    CoursePreset,
    CourseSelection,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
    ScheduleEventData,
    SchedulePageData,
    SharedFreeTimeRequest,
    SharedFreeTimeResponse,
)
from tiger_auth import Session, current_session
from tiger_schedule_store import (
    fetch_schedule,
    insert_schedule,
    list_schedules,
    load_page,
    remove_schedule,
    save_schedule,
)
from tiger_scheduler import (
    check_conflicts,
    check_name,
    class_event,
    course_presets,
    find_event,
    find_preset,
    find_user,
    free_time,
    page_data,
)

router: APIRouter = APIRouter(prefix="/api", tags=["Schedules"])


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
    current_user = find_user(data)

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
        for course in course_presets()
        if not search_term
        or search_term in " ".join(
            [course.title, course.course_name, course.category]
        ).casefold()
    ]


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

    check_conflicts(schedule, created)

    schedule.events.append(created)
    save_schedule(session, schedule)

    return created


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

    check_conflicts(schedule, event)

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
    event_index = find_event(schedule, event_id)

    del schedule.events[event_index]
    save_schedule(session, schedule)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
