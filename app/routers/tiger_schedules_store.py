"""Load and save each student's schedules in the Supabase schedules table."""

from datetime import date, datetime, timezone
from typing import Any, get_args
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from models.tiger_session import Session
from routers.tiger_profiles import session_profile
from routers.tiger_friends_store import friend_names, shared_rows
from models.tiger_schedules import (
    Classes,
    Schedule,
    ScheduleDefinition,
    ScheduleColor,
    ScheduleEvent,
    SchedulePageData,
    UserBase,
)

ZONE: ZoneInfo = ZoneInfo("America/Chicago")
TABLE: str = "schedules"
SHARED_FIELDS: str = "id,user_id,name,semester,color,sections,commitments"
FRIEND_LABEL: str = "Friend"
COLORS: tuple[str, ...] = get_args(ScheduleColor)
NAME_LIMIT: int = 60
UNTITLED: str = "Untitled schedule"
STAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"
CONFLICT: str = (
    "This schedule was changed somewhere else, maybe in another tab. "
    "Reload the page and try again."
)
TERMS: tuple[tuple[int, str], ...] = ((6, "Spring"), (8, "Summer"), (13, "Fall"))


def current_semester(today: date | None = None) -> str:
    """Name the academic term that contains a date.

    Args:
        today: Date to name, or None for today in Baton Rouge.

    Returns:
        A label such as "Fall 2026".
    """
    day = today or datetime.now(ZONE).date()
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


def to_row(schedule: Schedule) -> dict[str, Any]:
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
        "sections": [
            *(item.model_dump(mode="json") for item in classes),
            *schedule._kept.get("sections", []),
        ],
        "commitments": [
            *(item.model_dump(mode="json") for item in others),
            *schedule._kept.get("commitments", []),
        ],
    }


def parse_events(items: list[Any], kind: type) -> tuple[list[Any], list[Any]]:
    """Rebuild events from stored JSON, setting aside entries it can't read.

    Args:
        items: Stored event dicts.
        kind: Event model to build, Classes or ScheduleEvent.

    Returns:
        The events that validated, and the raw entries that did not, which
        are written back unchanged so saving never deletes them.
    """
    events, kept = [], []
    for item in items:
        try:
            events.append(kind(**item))
        except (TypeError, ValueError):
            kept.append(item)
    return events, kept


def clean_name(value: Any) -> str:
    """Make a stored schedule name safe to show.

    Args:
        value: The name column, possibly too long or blank.

    Returns:
        A non-blank name within the length limit.
    """
    text = " ".join(str(value or "").split())[:NAME_LIMIT]
    return text or UNTITLED


def stamp(value: Any) -> str | None:
    """Normalize a timestamp to a UTC string the database compares exactly.

    Args:
        value: An updated_at value read from or written to the database.

    Returns:
        The time as a UTC string ending in Z, or None when unreadable.
    """
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(STAMP_FORMAT)


def now_stamp() -> str:
    """Return the current time as a normalized UTC timestamp.

    Returns:
        The current time ending in Z.
    """
    return datetime.now(timezone.utc).strftime(STAMP_FORMAT)


def to_schedule(row: dict[str, Any]) -> Schedule:
    """Convert a database row into a Schedule.

    Args:
        row: Row from the schedules table.

    Returns:
        The matching Schedule whose id is the row id.
    """
    classes, odd_classes = parse_events(row.get("sections") or [], Classes)
    others, odd_others = parse_events(row.get("commitments") or [], ScheduleEvent)
    color = row.get("color")
    schedule = Schedule(
        id=str(row["id"]),
        name=clean_name(row.get("name")),
        color=color if color in COLORS else "blue",
        events=[*classes, *others],
    )
    schedule._kept = {"sections": odd_classes, "commitments": odd_others}
    schedule._version = stamp(row["updated_at"]) if row.get("updated_at") else None
    return schedule


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
    return [to_schedule(row) for row in rows or []]


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
    return to_schedule(rows[0])


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
    row = {**to_row(draft), "user_id": session.user_id, "updated_at": now_stamp()}
    rows = session.db.table(TABLE).insert(row).execute().data
    if not rows:
        raise HTTPException(status_code=400, detail="Could not save schedule.")
    return to_schedule(rows[0])


def save_schedule(session: Session, schedule: Schedule) -> None:
    """Persist one changed schedule.

    Args:
        session: Verified student and their database client.
        schedule: Schedule whose id names the row to update.

    Raises:
        HTTPException: With status 404 when the row is not the student's,
            or 409 when someone saved it after it was loaded.
    """
    moment = now_stamp()
    query = (
        session.db.table(TABLE)
        .update({**to_row(schedule), "updated_at": moment})
        .eq("id", schedule.id)
        .eq("user_id", session.user_id)
    )
    if schedule._version:
        query = query.eq("updated_at", schedule._version)
    rows = query.execute().data
    if not rows:
        if schedule._version and owns_schedule(session, schedule.id):
            raise HTTPException(status_code=409, detail=CONFLICT)
        raise HTTPException(status_code=404, detail="Schedule not found.")
    schedule._version = moment


def owns_schedule(session: Session, schedule_id: str) -> bool:
    """Tell whether the student still has a schedule with this id.

    Args:
        session: Verified student and their database client.
        schedule_id: Id of the schedule.

    Returns:
        True when the row exists and belongs to the student.
    """
    rows = (
        session.db.table(TABLE)
        .select("id")
        .eq("id", schedule_id)
        .eq("user_id", session.user_id)
        .execute()
        .data
    )
    return bool(rows)


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
    names = friend_names(session)
    owners: dict[str, list[Schedule]] = {}
    for share in shared_rows(session, SHARED_FIELDS):
        owners.setdefault(share["owner_id"], []).append(
            to_schedule(share["schedule"])
        )
    taken = {own_name} if own_name else set()
    return [
        UserBase(
            id=owner_id,
            username=unique_label(
                names.get(owner_id) or FRIEND_LABEL, taken
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
