"""Placeholder API handlers for friend requests."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/friends", tags=["Friends"])


class FriendRequestCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)


def _not_implemented(operation: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Friend request {operation} is not implemented yet.",
    )


@router.get("/requests/incoming")
def list_incoming_requests() -> None:
    """List friend requests received by the current user."""
    _not_implemented("listing")


@router.get("/requests/outgoing")
def list_outgoing_requests() -> None:
    """List friend requests sent by the current user."""
    _not_implemented("listing")


@router.post("/requests")
def send_friend_request(request: FriendRequestCreate) -> None:
    """Send a friend request to a username."""
    _not_implemented("sending")
