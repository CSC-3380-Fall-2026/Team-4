"""Keep account APIs available without requiring credentials at app startup."""

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from tiger_models import ProfileUpdate, UserAuthSchema, UserBase
from models.tiger_profile import ProfileRecord

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
        return create_client(url, key)
    except Exception as error:
        raise HTTPException(
            503, "Account services are temporarily unavailable."
        ) from error


@router.post("/login")
def login(credentials: UserAuthSchema) -> tuple[str, bool]:
    """Sign in using the existing email and password API contract.

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


@router.post("/signup")
def signup(credentials: UserAuthSchema) -> tuple[str, bool]:
    """Request account registration through the existing Supabase service.

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
        return auth_client().auth.get_user(token).user is not None
    except Exception:
        return False


def token_profile(token: str) -> dict[str, Any]:
    """Read account and profile data using a verified token and its owner ID.

    Args:
        token: Browser or API access token to verify with Supabase.

    Returns:
        Account information plus owned profile fields when available.

    Raises:
        HTTPException: If the token is invalid or account services are unavailable.
    """
    client: Client = auth_client()
    try:
        account = client.auth.get_user(token).user
    except Exception as error:
        raise HTTPException(401, "Please log in again.") from error
    if account is None:
        raise HTTPException(401, "Please log in again.")
    profile: dict[str, Any] = {
        "id": account.id,
        "username": account.user_metadata.get("username") or "",
        "email": account.email or "",
        "gpa": None,
        "courses": [],
        "data_error": False,
    }
    try:
        client.postgrest.auth(token)
        rows = (
            client.table("profiles")
            .select("id,username,gpa,courses")
            .eq("id", account.id)
            .limit(1)
            .execute()
            .data
        )
        if rows and rows[0]["id"] == account.id:
            row: ProfileRecord = ProfileRecord.model_validate(rows[0])
            profile["username"] = row.username or profile["username"]
            profile["gpa"] = row.gpa
            profile["courses"] = [course.model_dump() for course in row.courses]
    except Exception:
        profile["data_error"] = True
    return profile


def load_profile(request: Request) -> dict[str, Any] | None:
    """Return the browser's verified profile or None when signed out.

    Args:
        request: Browser request carrying an HTTP-only access-token cookie.

    Returns:
        This student's profile, or None for a missing or invalid session.

    Raises:
        HTTPException: If account services are unavailable.
    """
    token: str = request.cookies.get(AUTH_COOKIE, "")
    if not token:
        return None
    try:
        return token_profile(token)
    except HTTPException as error:
        if error.status_code == 401:
            return None
        raise


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

    def __init__(self, user_id: str, email: str, token: str):
        self.user_id = user_id
        self.email = email
        self.token = token
        self.db = user_client(token)


def user_client(token: str) -> Client:
    """Create a database client whose requests are limited to the token's owner."""
    client: Client = auth_client()
    client.postgrest.auth(token)
    return client


def current_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
) -> Session:
    """Identify the student from a bearer token or the browser login cookie."""
    token: str = (
        credentials.credentials
        if credentials
        else request.cookies.get(AUTH_COOKIE, "")
    )
    if not token:
        raise HTTPException(401, "Not signed in.")
    try:
        user = auth_client().auth.get_user(token).user
    except HTTPException:
        raise
    except Exception:
        user = None
    if user is None:
        raise HTTPException(401, "Session expired, please log in again.")
    return Session(user.id, user.email or "", token)


def _load_profile(session: Session) -> UserBase:
    rows = (
        session.db.table("profiles")
        .select("*")
        .eq("id", session.user_id)
        .execute()
        .data
    )
    row = rows[0] if rows else {}
    return UserBase(
        id=session.user_id,
        username=row.get("username"),
        email=row.get("email") or session.email,
        gpa=float(row["gpa"]) if row.get("gpa") is not None else None,
        completed_credit_hours=row.get("completed_credit_hours") or 0,
        courses=row.get("courses") or [],
    )


@router.get("/api/profile")
def get_profile(session: Session = Depends(current_session)) -> UserBase:
    """Return only the signed-in student's saved profile."""
    return _load_profile(session)


@router.put("/api/profile")
def update_profile(
    update: ProfileUpdate, session: Session = Depends(current_session)
) -> UserBase:
    """Save the signed-in student's username, GPA, credit hours, and courses."""
    row = {
        "id": session.user_id,
        "email": session.email,
        "username": (update.username or "").strip() or None,
        "gpa": update.gpa,
        "completed_credit_hours": update.completed_credit_hours,
        "courses": update.courses,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.db.table("profiles").upsert(row).execute()
    return _load_profile(session)
