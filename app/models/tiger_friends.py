"""Request bodies for the friends and schedule-sharing API."""

from pydantic import BaseModel, Field


class FriendRequestIn(BaseModel):
    """Request body naming the user to befriend."""

    username: str = Field(min_length=1, max_length=100)


class ScheduleShareIn(BaseModel):
    """Request body naming a schedule and the friend to share it with."""

    schedule_id: str
    friend_id: str
