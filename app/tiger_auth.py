"""Keep account APIs available without requiring credentials at app startup."""

import os
from pathlib import Path
from typing import Any, cast

import requests
from dotenv import load_dotenv
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from supabase import Client, ClientOptions, create_client

from models.tiger_profile import (
    ProfileCourse,
    ProfileRecord,
    ProfileUpdate,
    UserAuthSchema,
)
from models.tiger_schedule import UserBase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")
router: APIRouter = APIRouter()
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


@router.post("/login")
def login_api(credentials: UserAuthSchema) -> dict[str, str]:
    """Sign in through the JSON API.

    Args:
        credentials: Student email and password.

    Returns:
        The access token and its type.

    Raises:
        HTTPException: 401 when the email or password is wrong.
    """
    message, accepted = login(credentials)
    if not accepted:
        raise HTTPException(401, message)
    return {"access_token": message, "token_type": "bearer"}


@router.post("/signup")
def signup_api(credentials: UserAuthSchema) -> dict[str, Any]:
    """Register through the JSON API.

    Args:
        credentials: Student email and chosen password.

    Returns:
        Confirmation that the account was requested, with next steps.

    Raises:
        HTTPException: 400 when registration is refused.
    """
    message, accepted = signup(credentials)
    if not accepted:
        raise HTTPException(400, message)
    return {"created": True, "message": message}


@router.post("/logout")
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


@router.get("/validateToken")
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


def session_card(session: "Session") -> dict[str, Any]:
    """Read account and profile data for an already verified session.

    Args:
        session: The verified student and their database client.

    Returns:
        Account information plus owned profile fields when available.
    """
    profile: dict[str, Any] = {
        "id": session.user_id,
        "username": session.meta.get("username") or "",
        "email": session.email,
        "gpa": None,
        "completed_credit_hours": 0,
        "courses": [],
        "data_error": False,
    }
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
        if rows and rows[0]["id"] == session.user_id:
            row: ProfileRecord = ProfileRecord.model_validate(
                {**rows[0], "courses": []}
            )
            profile["username"] = row.username or profile["username"]
            profile["gpa"] = row.gpa
            profile["completed_credit_hours"] = row.completed_credit_hours
            profile["courses"] = readable_courses(rows[0].get("courses"))
    except Exception:
        profile["data_error"] = True
    return profile


def token_profile(token: str) -> dict[str, Any]:
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


@router.get("/getUser")
def get_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Return only the profile owned by the verified API caller.

    Args:
        credentials: Bearer token identifying the caller.

    Returns:
        The caller's own account and profile information.
    """
    return token_profile(credentials.credentials)


validateToken = validate_token
getUser = get_user


class Session:
    """A verified student plus a database client that acts as that student."""

    def __init__(
        self,
        user_id: str,
        email: str,
        token: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Store the student's identity and build their scoped client.

        Args:
            user_id: Verified Supabase user ID.
            email: Verified account email.
            token: Access token used for database requests.
            meta: Verified account metadata, such as the username.
        """
        self.user_id = user_id
        self.email = email
        self.token = token
        self.meta = meta or {}
        self.db = user_client(token)


class LoginRequired(Exception):
    """Signal that a browser page needs a signed-in student."""


def user_client(token: str) -> Client:
    """Create a database client whose requests are limited to the token's owner."""
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
    return Session(user.id, user.email or "", token, meta)


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
    response: RedirectResponse = RedirectResponse("/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE)
    response.headers["Cache-Control"] = "no-store"
    return response


def session_profile(session: Session) -> UserBase:
    """Read the session owner's saved profile row.

    Args:
        session: The verified student and their database client.

    Returns:
        The saved profile, or defaults when no row exists.
    """
    # The client types rows as generic JSON; profile rows are JSON objects.
    rows = cast(
        list[dict[str, Any]],
        session.db.table("profiles")
        .select("*")
        .eq("id", session.user_id)
        .execute()
        .data,
    )
    row: dict[str, Any] = rows[0] if rows else {}
    return UserBase(
        id=session.user_id,
        username=row.get("username"),
        email=str(row.get("email") or session.email),
        gpa=float(row["gpa"]) if row.get("gpa") is not None else None,
        completed_credit_hours=row.get("completed_credit_hours") or 0,
        courses=row.get("courses") or [],
    )


@router.get("/api/profile")
def get_profile(session: Session = Depends(current_session)) -> UserBase:
    """Return only the signed-in student's saved profile."""
    return session_profile(session)


def save_profile(session: Session, fields: dict[str, Any]) -> UserBase:
    """Store validated profile fields for the session's own student.

    Args:
        session: The verified student and their database client.
        fields: Username, GPA, credit hours, and courses to save.

    Returns:
        The profile as saved.
    """
    row: dict[str, Any] = {
        **fields,
        "id": session.user_id,
        "email": session.email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.db.table("profiles").upsert(row).execute()
    return session_profile(session)


@router.put("/api/profile")
def update_profile(
    update: ProfileUpdate, session: Session = Depends(current_session)
) -> UserBase:
    """Save the signed-in student's username, GPA, credit hours, and courses.

    Args:
        update: New profile values.
        session: The verified student making the request.
    """
    return save_profile(
        session,
        {
            "username": (update.username or "").strip() or None,
            "gpa": update.gpa,
            "completed_credit_hours": update.completed_credit_hours,
            "courses": [course.model_dump() for course in update.courses],
        },
    )
