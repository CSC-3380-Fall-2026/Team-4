"""Keep account APIs available without requiring credentials at app startup."""

import os
from pathlib import Path
from typing import Any, cast

import requests
from dotenv import load_dotenv
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from supabase import Client, ClientOptions, create_client

from tiger_views import redirect_to

from models.tiger_profile import (
    AccountCard,
    ProfileCourse,
    ProfileRecord,
    UserAuthSchema,
)
from models.tiger_schedule import UserBase
from models.tiger_session import Session

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")
security: HTTPBearer = HTTPBearer()
optional_security: HTTPBearer = HTTPBearer(auto_error=False)
AUTH_COOKIE: str = "tiger_access"


def auth_client() -> Client:
    """Create a separate Supabase client for one account operation.

    Returns:
        A client configured with server environment variables.

    Raises:
        HTTPException: If account service settings are missing or invalid.
    """
    url: str = os.getenv("SUPABASE_URL", "").strip()
    key: str = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise HTTPException(
            503, "Account services are temporarily unavailable."
        )
    try:
        # One-off clients: no stored session and no background token refresh,
        # so each login doesn't leave a refresh timer running in the server.
        options = ClientOptions(auto_refresh_token=False, persist_session=False)
        return create_client(url, key, options)
    except Exception as error:
        raise HTTPException(
            503, "Account services are temporarily unavailable."
        ) from error


def login(credentials: UserAuthSchema) -> tuple[str, bool]:
    """Sign in with Supabase for the HTML login form.

    Args:
        credentials: Student email and password.

    Returns:
        An access token and True on success, or a safe message and False.
    """
    client: Client = auth_client()
    try:
        result = client.auth.sign_in_with_password(
            {
                "email": str(credentials.email),
                "password": credentials.password,
            }
        )
        if result.session:
            return result.session.access_token, True
    except Exception:
        pass
    return (
        "Check your email and password, and confirm your email if required.",
        False,
    )


def signup(credentials: UserAuthSchema) -> tuple[str, bool]:
    """Request account registration with Supabase for the HTML signup form.

    Args:
        credentials: Student email and chosen password.

    Returns:
        A confirmation message and whether the request was accepted.
    """
    client: Client = auth_client()
    try:
        result = client.auth.sign_up(
            {
                "email": str(credentials.email),
                "password": credentials.password,
            }
        )
        if result.user:
            return "Check your email for confirmation, then log in.", True
    except Exception:
        pass
    return (
        "Registration could not be completed. Try logging in or try again later.",
        False,
    )


def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """Revoke the supplied access token without sharing account client state.

    Args:
        credentials: Bearer token belonging to the account being signed out.

    Returns:
        Whether Supabase accepted the sign-out request.
    """
    auth_client()
    try:
        result = requests.post(
            os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/logout",
            headers={
                "apikey": os.environ["SUPABASE_KEY"],
                "Authorization": "Bearer " + credentials.credentials,
            },
            timeout=10,
        )
        return result.status_code in (200, 204)
    except requests.RequestException:
        return False


def validate_token(token: str) -> bool:
    """Validate an access token with Supabase.

    Args:
        token: Access token to verify.

    Returns:
        True only when Supabase returns a verified user.
    """
    try:
        result = auth_client().auth.get_user(token)
    except Exception:
        return False
    return result is not None and result.user is not None


def readable_courses(raw: Any) -> list[dict[str, Any]]:
    """Keep the saved courses that have the expected shape.

    One malformed entry must not hide the whole profile, or the student
    could never reach the form to fix it.

    Args:
        raw: The profile's stored courses value.

    Returns:
        Valid course dicts; anything else is skipped.
    """
    courses: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            courses.append(ProfileCourse.model_validate(item).model_dump())
        except ValidationError:
            continue
    return courses


def session_card(session: Session) -> AccountCard:
    """Read account and profile data for an already verified session.

    Args:
        session: The verified student and their database client.

    Returns:
        Account information plus owned profile fields when available.
    """
    card: AccountCard = AccountCard(
        id=session.user_id,
        email=session.email,
        username=session.meta.get("username") or "",
    )
    try:
        # The client types rows as generic JSON; profile rows are JSON objects.
        rows = cast(
            list[dict[str, Any]],
            session.db.table("profiles")
            .select("id,username,gpa,completed_credit_hours,courses")
            .eq("id", session.user_id)
            .limit(1)
            .execute()
            .data,
        )
        saved: dict[str, Any] = rows[0] if rows else {}
        if saved.get("id") == session.user_id:
            row: ProfileRecord = ProfileRecord.model_validate(
                {**saved, "courses": []}
            )
            card = card.model_copy(
                update={
                    "username": row.username or card.username,
                    "gpa": row.gpa,
                    "completed_credit_hours": row.completed_credit_hours,
                    "courses": [
                        ProfileCourse(**course)
                        for course in readable_courses(saved.get("courses"))
                    ],
                }
            )
    except Exception:
        card = card.model_copy(update={"data_error": True})
    return card


def token_profile(token: str) -> AccountCard:
    """Read account and profile data using a verified token and its owner ID.

    Args:
        token: Browser or API access token to verify with Supabase.

    Returns:
        Account information plus owned profile fields when available.

    Raises:
        HTTPException: If the token is invalid or account services are unavailable.
    """
    session: Session | None = verify_token(token)
    if session is None:
        raise HTTPException(401, "Please log in again.")
    return session_card(session)


class LoginRequired(Exception):
    """Signal that a browser page needs a signed-in student."""


def user_client(token: str) -> Client:
    """Create a database client whose requests are limited to the token's owner.

    Args:
        token: The student's verified access token.

    Returns:
        A client that sends the token with every database request.

    Raises:
        HTTPException: If account services are unavailable.
    """
    client: Client = auth_client()
    client.postgrest.auth(token)
    return client


def verify_token(token: str) -> Session | None:
    """Ask Supabase to verify an access token's signature and expiry.

    Args:
        token: Access token from a cookie or bearer header.

    Returns:
        The verified session, or None for a missing, invalid or expired token.

    Raises:
        HTTPException: If account services are unavailable.
    """
    if not token:
        return None
    try:
        result = auth_client().auth.get_user(token)
    except HTTPException:
        raise
    except Exception:
        return None
    user = result.user if result is not None else None
    if user is None:
        return None
    meta: dict[str, Any] = getattr(user, "user_metadata", None) or {}
    return Session(user.id, user.email or "", token, user_client(token), meta)


def request_token(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> str:
    """Pick the bearer token if present, otherwise the login cookie.

    Args:
        request: Current request, which may carry the login cookie.
        credentials: Optional bearer token from the Authorization header.

    Returns:
        The token, or an empty string when none was sent.
    """
    if credentials:
        return credentials.credentials
    return request.cookies.get(AUTH_COOKIE, "")


def current_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
) -> Session:
    """Identify the student from a bearer token or the browser login cookie.

    Args:
        request: Current request, which may carry the login cookie.
        credentials: Optional bearer token from the Authorization header.

    Returns:
        The verified session.

    Raises:
        HTTPException: With status 401 when not signed in or expired.
    """
    token: str = request_token(request, credentials)
    if not token:
        raise HTTPException(401, "Not signed in.")
    session: Session | None = verify_token(token)
    if session is None:
        raise HTTPException(401, "Session expired, please log in again.")
    return session


def require_login(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
) -> Session:
    """Allow a page request only from a student with a Supabase-verified token.

    Args:
        request: Current request, which may carry the login cookie.
        credentials: Optional bearer token from the Authorization header.

    Returns:
        The verified session, shared with the page handler.

    Raises:
        LoginRequired: When the token is missing, invalid or expired.
    """
    session: Session | None = verify_token(request_token(request, credentials))
    if session is None:
        raise LoginRequired()
    return session


def login_redirect(request: Request, error: Exception) -> RedirectResponse:
    """Send a signed-out browser to the login page and drop its stale cookie.

    Args:
        request: The request that needed a login.
        error: The LoginRequired signal.

    Returns:
        An uncached 303 redirect to /login.
    """
    return signed_out()


def signed_out() -> RedirectResponse:
    """Send the browser to /login with its login cookie removed.

    Returns:
        An uncached 303 redirect to /login that deletes the login cookie.
    """
    response: RedirectResponse = redirect_to("/login")
    response.delete_cookie(AUTH_COOKIE)
    return response


def profile_row(session: Session, columns: str = "*") -> dict[str, Any]:
    """Read columns of the session owner's profile row.

    Args:
        session: The verified student and their database client.
        columns: PostgREST column list to select.

    Returns:
        The row, or an empty dict when the student has no profile yet.
    """
    # The client types rows as generic JSON; profile rows are JSON objects.
    rows = cast(
        list[dict[str, Any]],
        session.db.table("profiles")
        .select(columns)
        .eq("id", session.user_id)
        .execute()
        .data,
    )
    return rows[0] if rows else {}


def session_profile(session: Session) -> UserBase:
    """Read the session owner's saved profile row.

    Args:
        session: The verified student and their database client.

    Returns:
        The saved profile, or defaults when no row exists.
    """
    row: dict[str, Any] = profile_row(session)
    return UserBase(
        id=session.user_id,
        username=row.get("username"),
        email=str(row.get("email") or session.email),
        gpa=float(row["gpa"]) if row.get("gpa") is not None else None,
        completed_credit_hours=row.get("completed_credit_hours") or 0,
        courses=row.get("courses") or [],
    )


def save_profile(session: Session, profile: ProfileRecord) -> UserBase:
    """Store validated profile fields for the session's own student.

    Args:
        session: The verified student and their database client.
        profile: Username, GPA, credit hours, and courses to save.

    Returns:
        The profile as saved.
    """
    row: dict[str, Any] = {
        **profile.model_dump(),
        "id": session.user_id,
        "email": session.email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.db.table("profiles").upsert(row).execute()
    return session_profile(session)
