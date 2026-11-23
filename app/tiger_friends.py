"""Friends and schedule-sharing API for Tiger Scheduler."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from models.tiger_friends import FriendRequestIn, ScheduleShareIn
from tiger_auth import Session, current_session

router = APIRouter(prefix="/api/friends", tags=["friends"])
logger = logging.getLogger(__name__)

SHARED_COLUMNS: str = "id,name,semester,sections"
UNNAMED: str = "Student"



def pair_filter(left: str, right: str) -> str:
    """Build a filter matching a friendship row between two students.

    Args:
        left: First student id.
        right: Second student id.

    Returns:
        A PostgREST or_() filter for either direction.
    """
    return (
        f"and(requester_id.eq.{left},addressee_id.eq.{right}),"
        f"and(requester_id.eq.{right},addressee_id.eq.{left})"
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


def find_student(session: Session, username: str) -> str | None:
    """Look up a student's id by username without reading their profile.

    Profiles are private, so this calls a database function that returns
    only the id for an exact (case-insensitive) username.

    Args:
        session: Authenticated session.
        username: Username to look up.

    Returns:
        The student's id, or None when no student has that username.
    """
    data = (
        session.db.rpc("profile_id_for_username", {"name": username})
        .execute()
        .data
    )
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict):
        data = next(iter(data.values()), None)
    return str(data) if data else None


def own_username(session: Session) -> str | None:
    """Read the signed-in student's own username.

    Args:
        session: Authenticated session.

    Returns:
        The username, or None when it has not been set.
    """
    rows = (
        session.db.table("profiles")
        .select("username")
        .eq("id", session.user_id)
        .execute()
        .data
    )
    return (rows[0].get("username") or None) if rows else None


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


def existing_error(row: dict[str, Any], user_id: str, name: str) -> HTTPException:
    """Explain why a new friend request duplicates an existing row.

    Args:
        row: The existing friendship row.
        user_id: The signed-in student's id.
        name: The other student's username.

    Returns:
        A 409 error with a message for the student.
    """
    if row["status"] == "accepted":
        return HTTPException(409, f"You are already friends with {name}.")
    if row["requester_id"] == user_id:
        return HTTPException(409, f"You already sent {name} a friend request.")
    return HTTPException(
        409, f"{name} already sent you a friend request. Accept it below."
    )


@router.get("/me")
def friends_account(session: Session = Depends(current_session)) -> dict:
    """Confirm the authenticated account used by Friends APIs.

    Args:
        session: Authenticated session.

    Returns:
        Dict holding the user id and username.
    """
    return {"user_id": session.user_id, "username": own_username(session)}


@router.post("/requests", status_code=201)
def send_request(
    request: FriendRequestIn,
    session: Session = Depends(current_session),
) -> dict:
    """Send a request to an existing account by exact username.

    Args:
        request: Body with the target username.
        session: Authenticated session.

    Returns:
        Dict with a message and the created request row.
    """
    username = request.username.strip().lstrip("@").strip()
    if not username:
        raise HTTPException(422, "Username is required.")
    if not own_username(session):
        raise HTTPException(
            400, "Set a username on your profile before adding friends."
        )
    friend_id = find_student(session, username)
    if friend_id is None:
        raise HTTPException(404, f"No student has the username {username}.")
    if friend_id == session.user_id:
        raise HTTPException(400, "You cannot friend yourself.")
    existing = (
        session.db.table("friendships")
        .select("id,requester_id,status")
        .or_(pair_filter(session.user_id, friend_id))
        .execute()
        .data
    )
    if existing:
        raise existing_error(existing[0], session.user_id, username)
    result = (
        session.db.table("friendships")
        .insert({
            "requester_id": session.user_id,
            "addressee_id": friend_id,
            "status": "pending",
        })
        .execute()
    )
    name = friend_names(session).get(friend_id, username)
    return {"message": f"Friend request sent to {name}.", "request": result.data[0]}


@router.post("/requests/{request_id}/accept")
def accept_request(
    request_id: str,
    session: Session = Depends(current_session),
) -> dict:
    """Accept a pending friend request addressed to the user.

    Args:
        request_id: Id of the friendship row.
        session: Authenticated session.

    Returns:
        Dict with a confirmation message.
    """
    result = (
        session.db.table("friendships")
        .update({"status": "accepted"})
        .eq("id", request_id)
        .eq("addressee_id", session.user_id)
        .eq("status", "pending")
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Pending friend request not found.")
    return {"message": "Friend request accepted."}


@router.delete("/requests/{request_id}")
def reject_request(
    request_id: str,
    session: Session = Depends(current_session),
) -> dict:
    """Decline an incoming request or cancel one the user sent.

    Args:
        request_id: Id of the friendship row.
        session: Authenticated session.

    Returns:
        Dict with a confirmation message.
    """
    result = (
        session.db.table("friendships")
        .delete()
        .eq("id", request_id)
        .eq("status", "pending")
        .or_(mine_filter(session.user_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Pending friend request not found.")
    if result.data[0]["requester_id"] == session.user_id:
        return {"message": "Friend request canceled."}
    return {"message": "Friend request declined."}


@router.get("/shares")
def list_shares(session: Session = Depends(current_session)) -> list[dict]:
    """List the friends each of the user's schedules is shared with.

    Args:
        session: Authenticated session.

    Returns:
        Share rows with the friend's username.
    """
    current = {
        other_id(row, session.user_id)
        for row in friendship_rows(session) if row["status"] == "accepted"
    }
    rows = (
        session.db.table("schedule_shares")
        .select("id,schedule_id,friend_id")
        .eq("owner_id", session.user_id)
        .execute()
        .data
    )
    rows = [row for row in rows if row["friend_id"] in current]
    names = friend_names(session) if rows else {}
    return [
        {**row, "username": names.get(row["friend_id"], UNNAMED)}
        for row in rows
    ]


@router.post("/shares", status_code=201)
def share_schedule(
    request: ScheduleShareIn,
    session: Session = Depends(current_session),
) -> dict:
    """Share an owned schedule with an accepted friend.

    Args:
        request: Body with schedule and friend ids.
        session: Authenticated session.

    Returns:
        Dict with a message and the share row.
    """
    schedules = (
        session.db.table("schedules")
        .select("id")
        .eq("id", request.schedule_id)
        .eq("user_id", session.user_id)
        .execute()
        .data
    )
    if not schedules:
        raise HTTPException(404, "Schedule not found.")
    if not is_friend(session, request.friend_id):
        raise HTTPException(403, "You can only share with accepted friends.")
    existing = (
        session.db.table("schedule_shares")
        .select("id,schedule_id,friend_id")
        .eq("schedule_id", request.schedule_id)
        .eq("friend_id", request.friend_id)
        .execute()
        .data
    )
    if existing:
        return {"message": "Schedule already shared.", "share": existing[0]}
    result = (
        session.db.table("schedule_shares")
        .insert({
            "schedule_id": request.schedule_id,
            "owner_id": session.user_id,
            "friend_id": request.friend_id,
        })
        .execute()
    )
    return {"message": "Schedule shared.", "share": result.data[0]}


@router.delete("/shares/{share_id}")
def stop_sharing(
    share_id: str,
    session: Session = Depends(current_session),
) -> dict:
    """Stop sharing a schedule the user owns.

    Args:
        share_id: Id of the share row.
        session: Authenticated session.

    Returns:
        Dict with a confirmation message.
    """
    result = (
        session.db.table("schedule_shares")
        .delete()
        .eq("id", share_id)
        .eq("owner_id", session.user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Shared schedule not found.")
    return {"message": "Schedule sharing stopped."}


@router.delete("/{friendship_id}")
def remove_friend(
    friendship_id: str,
    session: Session = Depends(current_session),
) -> dict:
    """Remove an accepted friendship and every share between the two.

    Args:
        friendship_id: Id of the friendship row.
        session: Authenticated session.

    Returns:
        Dict with a confirmation message.
    """
    result = (
        session.db.table("friendships")
        .delete()
        .eq("id", friendship_id)
        .eq("status", "accepted")
        .or_(mine_filter(session.user_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Friendship not found.")
    former = other_id(result.data[0], session.user_id)
    me = session.user_id
    (
        session.db.table("schedule_shares")
        .delete()
        .or_(
            f"and(owner_id.eq.{me},friend_id.eq.{former}),"
            f"and(owner_id.eq.{former},friend_id.eq.{me})"
        )
        .execute()
    )
    return {"message": "Friend removed."}


def is_friend(session: Session, other: str) -> bool:
    """Check that the session's student has an accepted friendship with another.

    Args:
        session: Authenticated session.
        other: Id of the other student.

    Returns:
        True when an accepted friendship exists in either direction.
    """
    rows = (
        session.db.table("friendships")
        .select("id")
        .eq("status", "accepted")
        .or_(pair_filter(session.user_id, other))
        .execute()
        .data
    )
    return bool(rows)


def shared_rows(session: Session, columns: str = SHARED_COLUMNS) -> list[dict]:
    """Return schedules shared with the student by accepted friends.

    Args:
        session: Authenticated session.
        columns: Schedule columns to select.

    Returns:
        List of dicts with the owner id and the schedule row.
    """
    shares = (
        session.db.table("schedule_shares")
        .select("schedule_id,owner_id")
        .eq("friend_id", session.user_id)
        .execute()
        .data
    )
    results = []
    for share in shares:
        if not is_friend(session, share["owner_id"]):
            continue
        rows = (
            session.db.table("schedules")
            .select(columns)
            .eq("id", share["schedule_id"])
            .eq("user_id", share["owner_id"])
            .execute()
            .data
        )
        results.extend(
            {"owner_id": share["owner_id"], "schedule": row} for row in rows
        )
    return results


@router.get("/shared-with-me")
def shared_schedules(session: Session = Depends(current_session)) -> list[dict]:
    """Return only course sections from schedules shared by accepted friends.

    Args:
        session: Authenticated session.

    Returns:
        List of dicts with owner id and schedule.
    """
    return shared_rows(session)


def describe_row(row: dict[str, Any], user_id: str, names: dict[str, str]) -> dict:
    """Turn a friendship row into what the Friends page shows.

    Args:
        row: Friendship row.
        user_id: The signed-in student's id.
        names: Usernames by student id.

    Returns:
        The row id, the other student's id, and their username.
    """
    other = other_id(row, user_id)
    return {"id": row["id"], "user_id": other, "username": names.get(other, UNNAMED)}


@router.get("/requests")
def list_requests(session: Session = Depends(current_session)) -> dict:
    """List pending friend requests sent to and by this account.

    Each entry's id is what accepting, declining, or canceling takes:
    POST /api/friends/requests/{id}/accept or DELETE /api/friends/requests/{id}.

    Args:
        session: Authenticated session.

    Returns:
        Dict with incoming and outgoing requests, each naming the other student.
    """
    me = session.user_id
    pending = [
        row for row in friendship_rows(session) if row["status"] == "pending"
    ]
    names = friend_names(session) if pending else {}
    return {
        "incoming": [
            describe_row(row, me, names)
            for row in pending if row["addressee_id"] == me
        ],
        "outgoing": [
            describe_row(row, me, names)
            for row in pending if row["requester_id"] == me
        ],
    }


@router.get("/list")
def list_friends(session: Session = Depends(current_session)) -> dict:
    """List accepted friendships and pending requests for this account.

    Args:
        session: Authenticated session.

    Returns:
        Dict with friends, incoming and outgoing requests, each naming the
        other student.
    """
    rows = friendship_rows(session)
    names = friend_names(session) if rows else {}
    me = session.user_id
    pending = [row for row in rows if row["status"] == "pending"]
    return {
        "friends": [
            describe_row(row, me, names)
            for row in rows if row["status"] == "accepted"
        ],
        "incoming_requests": [
            describe_row(row, me, names)
            for row in pending if row["addressee_id"] == me
        ],
        "outgoing_requests": [
            describe_row(row, me, names)
            for row in pending if row["requester_id"] == me
        ],
    }
