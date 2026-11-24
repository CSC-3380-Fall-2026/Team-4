"""Validate account credentials, and the JSON login and signup responses."""

from pydantic import BaseModel, EmailStr


class UserAuthSchema(BaseModel):
    """Email and password submitted for login or signup."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """The access token returned by a successful JSON login.

    Attributes:
        access_token: The token to send as a bearer credential.
        token_type: The token scheme, always "bearer".
    """

    access_token: str
    token_type: str = "bearer"


class SignupResponse(BaseModel):
    """Confirmation that a signup was requested, with next steps.

    Attributes:
        created: True when the signup was requested.
        message: What the student should do next.
    """

    created: bool
    message: str
