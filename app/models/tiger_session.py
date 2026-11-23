"""The verified student a request acts for."""

from dataclasses import dataclass, field
from typing import Any

from supabase import Client


@dataclass
class Session:
    """A verified student plus a database client that acts as that student.

    Attributes:
        user_id: Verified Supabase user ID.
        email: Verified account email.
        token: Access token used for database requests.
        db: Client that sends the token with every database request.
        meta: Verified account metadata, such as the username.
    """

    user_id: str
    email: str
    token: str
    db: Client
    meta: dict[str, Any] = field(default_factory=dict)
