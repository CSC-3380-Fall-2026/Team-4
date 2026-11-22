"""Friends and schedule-sharing API for Tiger Scheduler."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiger_auth import Session, current_session

router = APIRouter(prefix="/api/friends", tags=["friends"])


class FriendRequestIn(BaseModel):
    """Request body naming the user to befriend."""

    username: str = Field(min_length=1, max_length=100)


@router.get("/me")
def friends_account(session: Session = Depends(current_session)) -> dict:
    """Confirm the authenticated account used by Friends APIs.

    Args:
        session: Authenticated session.

    Returns:
        Dict holding the user id.
    """
    return {"user_id": session.user_id}


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
    username = request.username.strip()
    if not username:
        raise HTTPException(422, "Username is required.")

    friend_id = session.db.rpc(
        "profile_id_for_username", {"name": username}
    ).execute().data

    if not friend_id:
        raise HTTPException(404, "Username not found.")

    if friend_id == session.user_id:
        raise HTTPException(400, "You cannot friend yourself.")

    existing = (
        session.db.table("friendships")
        .select("id")
        .or_(
            f"and(requester_id.eq.{session.user_id},addressee_id.eq.{friend_id}),"
            f"and(requester_id.eq.{friend_id},addressee_id.eq.{session.user_id})"
        )
        .execute()
        .data
    )

    if existing:
        raise HTTPException(409, "A friendship or request already exists.")

    result = (
        session.db.table("friendships")
        .insert({
            "requester_id": session.user_id,
            "addressee_id": friend_id,
            "status": "pending",
        })
        .execute()
    )

    return {"message": "Friend request sent.", "request": result.data[0]}


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
    """Reject a pending friend request addressed to the user.

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
        .eq("addressee_id", session.user_id)
        .eq("status", "pending")
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Pending friend request not found.")

    return {"message": "Friend request rejected."}


@router.delete("/{friendship_id}")
def remove_friend(
    friendship_id: str,
    session: Session = Depends(current_session),
) -> dict:
    """Remove an accepted friendship involving the logged-in user.

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
        .or_(
            f"requester_id.eq.{session.user_id},"
            f"addressee_id.eq.{session.user_id}"
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "Friendship not found.")

    return {"message": "Friend removed."}


class ScheduleShareIn(BaseModel):
    """Request body naming a schedule and the friend to share it with."""

    schedule_id: str
    friend_id: str


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

    friendship = (
        session.db.table("friendships")
        .select("id")
        .eq("status", "accepted")
        .or_(
            f"and(requester_id.eq.{session.user_id},addressee_id.eq.{request.friend_id}),"
            f"and(requester_id.eq.{request.friend_id},addressee_id.eq.{session.user_id})"
        )
        .execute()
        .data
    )

    if not friendship:
        raise HTTPException(403, "Only accepted friends can view shared schedules.")

    result = (
        session.db.table("schedule_shares")
        .upsert(
            {
                "schedule_id": request.schedule_id,
                "owner_id": session.user_id,
                "friend_id": request.friend_id,
            },
            on_conflict="schedule_id,friend_id",
        )
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


SHARED_COLUMNS: str = "id,name,semester,sections"


def is_friend(session: Session, other_id: str) -> bool:
    """Check that the session's student has an accepted friendship with another.

    Args:
        session: Authenticated session.
        other_id: Id of the other student.

    Returns:
        True when an accepted friendship exists in either direction.
    """
    rows = (
        session.db.table("friendships")
        .select("id")
        .eq("status", "accepted")
        .or_(
            f"and(requester_id.eq.{session.user_id},addressee_id.eq.{other_id}),"
            f"and(requester_id.eq.{other_id},addressee_id.eq.{session.user_id})"
        )
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

@router.get("/shared-by-me")
def shared_by_me(session: Session = Depends(current_session)) -> list[dict]:
    """List schedule shares created by the signed-in user."""
    return (
        session.db.table("schedule_shares")
        .select("id,schedule_id,friend_id")
        .eq("owner_id", session.user_id)
        .execute()
        .data
    )
@router.get("/shared-with-me")
def shared_schedules(session: Session = Depends(current_session)) -> list[dict]:
    """Return only course sections from schedules shared by accepted friends.

    Args:
        session: Authenticated session.

    Returns:
        List of dicts with owner id and schedule.
    """
    return shared_rows(session)


@router.get("/list")
def list_friends(session: Session = Depends(current_session)) -> dict:
    """List accepted friendships and pending requests for this account.

    Args:
        session: Authenticated session.

    Returns:
        Dict with friends, incoming and outgoing requests.
    """
    rows = (
        session.db.table("friendships")
        .select("id,requester_id,addressee_id,status")
        .or_(
            f"requester_id.eq.{session.user_id},"
            f"addressee_id.eq.{session.user_id}"
        )
        .execute()
        .data
    )

    for row in rows:
        other_id = (
            row["addressee_id"]
            if row["requester_id"] == session.user_id
            else row["requester_id"]
        )
        row["username"] = session.db.rpc(
            "username_for_friend", {"friend_user_id": other_id}
        ).execute().data
    return {
        "friends": [r for r in rows if r["status"] == "accepted"],
        "incoming_requests": [
            r for r in rows
            if r["status"] == "pending"
            and r["addressee_id"] == session.user_id
        ],
        "outgoing_requests": [
            r for r in rows
            if r["status"] == "pending"
            and r["requester_id"] == session.user_id
        ],
    }
