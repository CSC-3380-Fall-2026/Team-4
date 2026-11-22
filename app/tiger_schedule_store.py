"""Load and save each student's schedules in the Supabase schedules table."""

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException

from tiger_auth import Session, session_profile
from tiger_friends import shared_rows
from tiger_models import (
    Classes,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
    SchedulePageData,
    UserBase,
)

TABLE: str = "schedules"
SHARED_FIELDS: str = "id,name,semester,color,sections,commitments"
FRIEND_LABEL: str = "Friend"
TERMS: tuple[tuple[int, str], ...] = ((6, "Spring"), (8, "Summer"), (13, "Fall"))


def current_semester(today: date | None = None) -> str:
    """Name the academic term that contains a date.

    Args:
        today: Date to name, or None for the current date.

    Returns:
        A label such as "Fall 2026".
    """
    day = today or date.today()
    term = next(name for end, name in TERMS if day.month < end)
    return f"{term} {day.year}"


def schedule_semester(schedule: Schedule) -> str:
    """Pick the semester stored with a schedule.

    Args:
        schedule: Schedule being saved.

    Returns:
        The semester of its first class, or the current semester.
    """
    classes = [item for item in schedule.events if isinstance(item, Classes)]
    return classes[0].semester if classes else current_semester()


def schedule_to_row(schedule: Schedule) -> dict[str, Any]:
    """Convert a Schedule into database columns.

    Args:
        schedule: Schedule to store.

    Returns:
        Columns name, semester, color, sections and commitments.
    """
    classes = [e for e in schedule.events if isinstance(e, Classes)]
    others = [e for e in schedule.events if not isinstance(e, Classes)]
    return {
        "name": schedule.name,
        "semester": schedule_semester(schedule),
        "color": schedule.color,
        "sections": [item.model_dump(mode="json") for item in classes],
        "commitments": [item.model_dump(mode="json") for item in others],
    }


def parse_events(items: list[dict], kind: type) -> list[Any]:
    """Rebuild events from stored JSON, skipping entries of an unknown shape.

    Args:
        items: Stored event dicts.
        kind: Event model to build, Classes or ScheduleEvent.

    Returns:
        The events that validated.
    """
    events = []
    for item in items:
        try:
            events.append(kind(**item))
        except (TypeError, ValueError):
            continue
    return events


def row_to_schedule(row: dict[str, Any]) -> Schedule:
    """Convert a database row into a Schedule.

    Args:
        row: Row from the schedules table.

    Returns:
        The matching Schedule whose id is the row id.
    """
    classes = parse_events(row.get("sections") or [], Classes)
    others = parse_events(row.get("commitments") or [], ScheduleEvent)
    return Schedule(
        id=str(row["id"]),
        name=row["name"],
        color=row.get("color") or "blue",
        events=[*classes, *others],
    )


def list_schedules(session: Session) -> list[Schedule]:
    """Load every schedule owned by the signed-in student.

    Args:
        session: Verified student and their database client.

    Returns:
        Schedules in creation order.
    """
    rows = (
        session.db.table(TABLE)
        .select("*")
        .eq("user_id", session.user_id)
        .order("created_at")
        .execute()
        .data
    )
    return [row_to_schedule(row) for row in rows or []]


def fetch_schedule(session: Session, schedule_id: str) -> Schedule:
    """Load one schedule owned by the signed-in student.

    Args:
        session: Verified student and their database client.
        schedule_id: Id of the schedule.

    Returns:
        The schedule.

    Raises:
        HTTPException: With status 404 when it does not exist.
    """
    rows = (
        session.db.table(TABLE)
        .select("*")
        .eq("id", schedule_id)
        .eq("user_id", session.user_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return row_to_schedule(rows[0])


def insert_schedule(session: Session, definition: ScheduleDefinition) -> Schedule:
    """Create an empty schedule for the signed-in student.

    Args:
        session: Verified student and their database client.
        definition: Name and color of the schedule.

    Returns:
        The stored schedule with its database id.

    Raises:
        HTTPException: With status 400 when nothing was stored.
    """
    draft = Schedule(**definition.model_dump(), events=[])
    row = {**schedule_to_row(draft), "user_id": session.user_id}
    rows = session.db.table(TABLE).insert(row).execute().data
    if not rows:
        raise HTTPException(status_code=400, detail="Could not save schedule.")
    return row_to_schedule(rows[0])


def save_schedule(session: Session, schedule: Schedule) -> None:
    """Persist one changed schedule.

    Args:
        session: Verified student and their database client.
        schedule: Schedule whose id names the row to update.

    Raises:
        HTTPException: With status 404 when the row is not the student's.
    """
    changes = {
        **schedule_to_row(schedule),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    rows = (
        session.db.table(TABLE)
        .update(changes)
        .eq("id", schedule.id)
        .eq("user_id", session.user_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Schedule not found.")


def remove_schedule(session: Session, schedule_id: str) -> None:
    """Delete one schedule owned by the signed-in student.

    Args:
        session: Verified student and their database client.
        schedule_id: Id of the schedule.

    Raises:
        HTTPException: With status 404 when it does not exist.
    """
    rows = (
        session.db.table(TABLE)
        .delete()
        .eq("id", schedule_id)
        .eq("user_id", session.user_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Schedule not found.")


def owner_name(session: Session, owner_id: str) -> str | None:
    """Read a friend's username when the database allows it.

    Args:
        session: Verified student and their database client.
        owner_id: Id of the friend.

    Returns:
        The username, or None when it is missing or hidden.
    """
    rows = (
        session.db.table("profiles")
        .select("username")
        .eq("id", owner_id)
        .execute()
        .data
    )
    return (rows[0].get("username") or None) if rows else None


def unique_label(base: str, taken: set[str]) -> str:
    """Make a label that no earlier friend already uses.

    Args:
        base: Preferred label.
        taken: Labels already in use; the result is added to it.

    Returns:
        The base label, or the base with a counter.
    """
    label, count = base, 1
    while label in taken:
        count += 1
        label = f"{base} {count}"
    taken.add(label)
    return label


def friend_users(session: Session, own_name: str | None) -> list[UserBase]:
    """Build users for friends who shared schedules with the student.

    Args:
        session: Verified student and their database client.
        own_name: The student's username, kept out of friend labels.

    Returns:
        One user per friend holding only the schedules shared with the student.
    """
    owners: dict[str, list[Schedule]] = {}
    for share in shared_rows(session, SHARED_FIELDS):
        owners.setdefault(share["owner_id"], []).append(
            row_to_schedule(share["schedule"])
        )
    taken = {own_name} if own_name else set()
    return [
        UserBase(
            id=owner_id,
            username=unique_label(
                owner_name(session, owner_id) or FRIEND_LABEL, taken
            ),
            email="",
            schedules=schedules,
        )
        for owner_id, schedules in owners.items()
    ]


def load_page(session: Session) -> SchedulePageData:
    """Assemble the student's schedule page data from the database.

    Args:
        session: Verified student and their database client.

    Returns:
        The student plus friends who shared schedules; metrics are empty.
    """
    student = session_profile(session)
    student.schedules = list_schedules(session)
    return SchedulePageData(
        current_user_id=session.user_id,
        users=[student, *friend_users(session, student.username)],
        metrics={},
    )
