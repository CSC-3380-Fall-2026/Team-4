"""Friendship and schedule-sharing queries for Tiger Scheduler."""

import logging
from typing import Any

from models.tiger_friends import Friend
from models.tiger_schedules import UserBase
from models.tiger_session import Session

logger = logging.getLogger(__name__)

UNNAMED: str = "Student"


def pair_filter(
    left: str,
    right: str,
    columns: tuple[str, str] = ("requester_id", "addressee_id"),
) -> str:
    """Build a filter matching a row between two students in either direction.

    Args:
        left: First student id.
        right: Second student id.
        columns: The two student-id columns; friendship columns by default.

    Returns:
        A PostgREST or_() filter for either direction.
    """
    first, second = columns
    return (
        f"and({first}.eq.{left},{second}.eq.{right}),"
        f"and({first}.eq.{right},{second}.eq.{left})"
    )


def mine_filter(user_id: str) -> str:
    """Build a filter matching friendship rows involving one student.

    Args:
        user_id: The student's id.

    Returns:
        A PostgREST or_() filter.
    """
    return f"requester_id.eq.{user_id},addressee_id.eq.{user_id}"


def other_id(row: dict[str, Any], user_id: str) -> str:
    """Return the other student in a friendship row.

    Args:
        row: Friendship row.
        user_id: The signed-in student's id.

    Returns:
        The id of the other student.
    """
    if row["requester_id"] == user_id:
        return row["addressee_id"]
    return row["requester_id"]


def friend_names(session: Session) -> dict[str, str]:
    """Map every student linked to the signed-in student to their username.

    Covers friends and both directions of pending requests, through a
    database function that exposes only ids and usernames.

    Args:
        session: Authenticated session.

    Returns:
        Dict from student id to username, or an empty dict when the lookup
        fails (for example before database/tiger_setup.sql is re-run), so
        pages still load and show generic names instead of erroring.
    """
    try:
        rows = session.db.rpc("friend_profiles", {}).execute().data or []
    except Exception:
        logger.warning(
            "friend_profiles() lookup failed; re-run database/tiger_setup.sql "
            "in Supabase. Showing generic friend names for now.",
            exc_info=True,
        )
        return {}
    return {row["id"]: row.get("username") or UNNAMED for row in rows}


def friendship_rows(session: Session) -> list[dict[str, Any]]:
    """Read every friendship row involving the signed-in student.

    Args:
        session: Authenticated session.

    Returns:
        Friendship rows.
    """
    return (
        session.db.table("friendships")
        .select("id,requester_id,addressee_id,status")
        .or_(mine_filter(session.user_id))
        .execute()
        .data
    )


def is_friend(session: Session, other: str) -> bool:
    """Check that the session's student has an accepted friendship with another.

    The other id comes from the request, so it is compared in Python and
    never pasted into a filter.

    Args:
        session: Authenticated session.
        other: Id of the other student.

    Returns:
        True when another student is the other party of an accepted
        friendship; never for the student's own id.
    """
    return other != session.user_id and any(
        row["status"] == "accepted" and other_id(row, session.user_id) == other
        for row in friendship_rows(session)
    )


def shared_rows(session: Session, columns: str) -> list[dict]:
    """Return schedules shared with the student by accepted friends.

    The "read schedules shared with me" policy in database/tiger_setup.sql
    returns a schedule only when it is shared with the student and its
    owner is an accepted friend, so one query covers every share.

    Args:
        session: Authenticated session.
        columns: Schedule columns to select; must include user_id.

    Returns:
        List of dicts with the owner id and the schedule row, in share order.
    """
    shares = (
        session.db.table("schedule_shares")
        .select("schedule_id")
        .eq("friend_id", session.user_id)
        .execute()
        .data
    )
    ids = [share["schedule_id"] for share in shares]
    if not ids:
        return []
    rows = session.db.table("schedules").select(columns).in_("id", ids).execute().data
    found = {row["id"]: row for row in rows if row["user_id"] != session.user_id}
    return [
        {"owner_id": found[key]["user_id"], "schedule": found[key]}
        for key in ids if key in found
    ]


def describe_row(row: dict[str, Any], user_id: str, names: dict[str, str]) -> Friend:
    """Turn a friendship row into the other student, as the Friends page shows them.

    Args:
        row: Friendship row.
        user_id: The signed-in student's id.
        names: Usernames by student id.

    Returns:
        The row id, the other student's id, and their username.
    """
    other = other_id(row, user_id)
    return Friend(id=row["id"], user_id=other, username=names.get(other, UNNAMED))


def load_friends(session: Session) -> UserBase:
    """Read the signed-in student with their friends and pending requests.

    Args:
        session: Authenticated session.

    Returns:
        The student, with friends, incoming_requests and outgoing_requests filled.
    """
    me: str = session.user_id
    rows = friendship_rows(session)
    names = friend_names(session) if rows else {}
    user = UserBase(id=me, email=session.email)
    for row in rows:
        friend = describe_row(row, me, names)
        if row["status"] == "accepted":
            user.friends.append(friend)
        elif row["status"] == "pending" and row["addressee_id"] == me:
            user.incoming_requests.append(friend)
        elif row["status"] == "pending":
            user.outgoing_requests.append(friend)
    return user
