"""Validate account credentials."""

from pydantic import BaseModel, EmailStr


class UserAuthSchema(BaseModel):
    """Email and password submitted for login or signup."""

    email: EmailStr
    password: str

