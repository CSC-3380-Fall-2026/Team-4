"""Friends page, and the friends and schedule-sharing JSON API."""

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

import tiger_auth
from models.tiger_friends import FriendRequestIn, ScheduleShareIn, Student
from models.tiger_session import Session
from routers.tiger_friends_store import (
    friend_names,
    is_friend,
    load_friends,
    mine_filter,
    other_id,
    pair_filter,
    shared_rows,
)
from routers.tiger_profiles import profile_row
from tiger_auth import current_session, require_login
from tiger_views import render_page


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
    return profile_row(session, "username").get("username") or None


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


router: APIRouter = APIRouter()


@router.get("/friends", response_class=HTMLResponse)
def friends_page(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Open the existing Friends interface with shared navigation.

    Args:
        request: Browser request for the Friends page.
        session: The verified student; signed-out visitors go to login.

    Returns:
        The Friends page and its existing schedule-sharing controls.
    """
    return render_page(
        request, "tiger_friends.html", profile=tiger_auth.nav_profile(session)
    )


api: APIRouter = APIRouter(prefix="/api/friends", tags=["friends"])


@api.get("/me")
def friends_account(session: Session = Depends(current_session)) -> Student:
    """Confirm the authenticated account used by Friends APIs.

    Args:
        session: Authenticated session.

    Returns:
        The signed-in student's user id and username.
    """
    return Student(user_id=session.user_id, username=own_username(session))


@api.post("/requests", status_code=201)
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

    Raises:
        HTTPException: 422 for a blank username; 400 without your own
            username or when adding yourself; 404 for an unknown username;
            409 when a friendship or request already exists.
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


@api.post("/requests/{request_id}/accept")
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

    Raises:
        HTTPException: 404 when no pending request to the student matches.
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


@api.delete("/requests/{request_id}")
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

    Raises:
        HTTPException: 404 when no pending request involving the student matches.
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


@api.get("/shares")
def list_shares(session: Session = Depends(current_session)) -> list[dict]:
    """List the friends each of the user's schedules is shared with.

    Args:
        session: Authenticated session.

    Returns:
        Share rows with the friend's username.
    """
    names = {friend.user_id: friend.username for friend in load_friends(session).friends}
    # The client types rows as generic JSON; share rows are JSON objects.
    rows = cast(
        list[dict[str, Any]],
        session.db.table("schedule_shares")
        .select("id,schedule_id,friend_id")
        .eq("owner_id", session.user_id)
        .execute()
        .data,
    )
    return [
        {**row, "username": names[row["friend_id"]]}
        for row in rows if row["friend_id"] in names
    ]


@api.post("/shares", status_code=201)
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

    Raises:
        HTTPException: 404 for a schedule the student doesn't own, or 403
            when the other student is not an accepted friend.
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


@api.delete("/shares/{share_id}")
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

    Raises:
        HTTPException: 404 when the student owns no such share.
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


@api.delete("/{friendship_id}")
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

    Raises:
        HTTPException: 404 when no accepted friendship involving the student matches.
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
    (
        session.db.table("schedule_shares")
        .delete()
        .or_(pair_filter(session.user_id, former, ("owner_id", "friend_id")))
        .execute()
    )
    return {"message": "Friend removed."}


@api.get("/shared-with-me")
def shared_schedules(session: Session = Depends(current_session)) -> list[dict]:
    """Return only course sections from schedules shared by accepted friends.

    Args:
        session: Authenticated session.

    Returns:
        List of dicts with owner id and schedule.
    """
    return shared_rows(session)


@api.get("/requests")
def list_requests(session: Session = Depends(current_session)) -> dict:
    """List pending friend requests sent to and by this account.

    Each entry's id is what accepting, declining, or canceling takes:
    POST /api/friends/requests/{id}/accept or DELETE /api/friends/requests/{id}.

    Args:
        session: Authenticated session.

    Returns:
        Dict with incoming and outgoing requests, each naming the other student.
    """
    user = load_friends(session)
    return {"incoming": user.incoming_requests, "outgoing": user.outgoing_requests}


@api.get("/list")
def list_friends(session: Session = Depends(current_session)) -> dict:
    """List accepted friendships and pending requests for this account.

    Args:
        session: Authenticated session.

    Returns:
        Dict with friends, incoming and outgoing requests, each naming the
        other student.
    """
    user = load_friends(session)
    return {
        "friends": user.friends,
        "incoming_requests": user.incoming_requests,
        "outgoing_requests": user.outgoing_requests,
    }


# The page sits at the site root; the JSON routes above sit under /api/friends.
router.include_router(api)
