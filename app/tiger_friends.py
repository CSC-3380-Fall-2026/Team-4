"""Friends and schedule-sharing API for Tiger Scheduler."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tiger_auth import Session, current_session

router = APIRouter(prefix="/api/friends", tags=["friends"])


class FriendRequestIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)


@router.get("/me")
def friends_account(session: Session = Depends(current_session)):
    """Confirm the authenticated account used by Friends APIs."""
    return {"user_id": session.user_id}


@router.post("/requests", status_code=201)
def send_friend_request(
    request: FriendRequestIn,
    session: Session = Depends(current_session),
):
    """Send a request to an existing account by exact username."""
    username = request.username.strip()
    if not username:
        raise HTTPException(422, "Username is required.")

    matches = (
        session.db.table("profiles")
        .select("id,username")
        .eq("username", username)
        .execute()
        .data
    )

    if not matches:
        raise HTTPException(404, "Username not found.")

    friend_id = matches[0]["id"]

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
def accept_friend_request(
    request_id: str,
    session: Session = Depends(current_session),
):
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
def reject_friend_request(
    request_id: str,
    session: Session = Depends(current_session),
):
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
):
    """Remove an accepted friendship involving the logged-in user."""
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
    schedule_id: str
    friend_id: str


@router.post("/shares", status_code=201)
def share_schedule(
    request: ScheduleShareIn,
    session: Session = Depends(current_session),
):
    """Share an owned schedule with an accepted friend."""
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
):
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


@router.get("/shared-with-me")
def shared_with_me(session: Session = Depends(current_session)):
    """Return only course sections from schedules shared by accepted friends."""
    shares = (
        session.db.table("schedule_shares")
        .select("schedule_id,owner_id")
        .eq("friend_id", session.user_id)
        .execute()
        .data
    )

    results = []
    for share in shares:
        friendship = (
            session.db.table("friendships")
            .select("id")
            .eq("status", "accepted")
            .or_(
                f"and(requester_id.eq.{session.user_id},addressee_id.eq.{share['owner_id']}),"
                f"and(requester_id.eq.{share['owner_id']},addressee_id.eq.{session.user_id})"
            )
            .execute()
            .data
        )
        if not friendship:
            continue

        schedules = (
            session.db.table("schedules")
            .select("id,name,semester,sections")
            .eq("id", share["schedule_id"])
            .eq("user_id", share["owner_id"])
            .execute()
            .data
        )
        for schedule in schedules:
            results.append({
                "owner_id": share["owner_id"],
                "schedule": schedule,
            })

    return results


@router.get("/list")
def list_friends(session: Session = Depends(current_session)):
    """List accepted friendships and pending requests for this account."""
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
