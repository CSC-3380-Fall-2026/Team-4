"""this file will be for sending and listing friend requests"""
from fastapi import APIRouter, Depends, HTTPException
from tiger_auth import Session, current_session
from tiger_models import FriendRequestIn, FriendRequestOut, FriendRequestList

router = APIRouter()


def _to_out(row: dict) -> FriendRequestOut:
    return FriendRequestOut(
        id=row["id"],
        sender_username=row["sender_username"],
        recipient_username=row["recipient_username"],
        status=row["status"],
        created_at=row.get("created_at"),
    )


@router.post("/friend-requests")
def send_friend_request(body: FriendRequestIn, session: Session = Depends(current_session)) -> FriendRequestOut:
    mine = session.db.table("profiles").select("username").eq("id", session.user_id).execute().data
    my_username = mine[0]["username"] if mine else None
    if not my_username:
        raise HTTPException(status_code=400, detail="Set a username in your profile before sending requests")

    target = body.username.strip()
    recipient_id = session.db.rpc("profile_id_for_username", {"name": target}).execute().data
    if not recipient_id:
        raise HTTPException(status_code=404, detail=f"No student with the username '{target}'")
    if recipient_id == session.user_id:
        raise HTTPException(status_code=400, detail="You cannot send a friend request to yourself")

    # RLS only shows requests involving this account, so this covers both directions.
    existing = (
        session.db.table("friend_requests").select("sender_id")
        .or_(f"and(sender_id.eq.{session.user_id},recipient_id.eq.{recipient_id}),"
             f"and(sender_id.eq.{recipient_id},recipient_id.eq.{session.user_id})")
        .execute().data
    )
    if existing:
        if existing[0]["sender_id"] == session.user_id:
            raise HTTPException(status_code=409, detail="You already sent this student a friend request")
        raise HTTPException(status_code=409, detail="This student already sent you a request; check your incoming requests")

    row = {
        "sender_id": session.user_id,
        "recipient_id": recipient_id,
        "sender_username": my_username,
        "recipient_username": target,
    }
    data = session.db.table("friend_requests").insert(row).execute().data
    if not data:
        raise HTTPException(status_code=400, detail="Could not send friend request")
    return _to_out(data[0])


@router.get("/friend-requests")
def list_friend_requests(session: Session = Depends(current_session)) -> FriendRequestList:
    rows = (
        session.db.table("friend_requests").select("*")
        .order("created_at", desc=True).execute().data
    )
    incoming = [_to_out(r) for r in rows if r["recipient_id"] == session.user_id]
    outgoing = [_to_out(r) for r in rows if r["sender_id"] == session.user_id]
    return FriendRequestList(incoming=incoming, outgoing=outgoing)
