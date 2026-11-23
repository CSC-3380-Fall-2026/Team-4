"""Friends, and request bodies for the friends and schedule-sharing API."""

from pydantic import BaseModel, Field


class Friend(BaseModel):
    """Another student linked to the signed-in one by a friendship row.

    Attributes:
        id: The friendship row id, which accept, decline and remove take.
        user_id: The other student's id.
        username: The other student's username.
    """

    id: str
    user_id: str
    username: str


class Student(BaseModel):
    """The signed-in student, as GET /api/friends/me returns them."""

    user_id: str
    username: str | None


class FriendRequestIn(BaseModel):
    """Request body naming the user to befriend."""

    username: str = Field(min_length=1, max_length=100)


class ScheduleShareIn(BaseModel):
    """Request body naming a schedule and the friend to share it with."""

    schedule_id: str
    friend_id: str
