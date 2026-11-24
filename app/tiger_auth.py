"""Keep account APIs available without requiring credentials at app startup."""

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, ClientOptions, create_client

from tiger_views import redirect_to

from models.tiger_accounts import UserAuthSchema
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
        An access token and True on success, or a safe message and False
        when Supabase refused the email or password.

    Raises:
        HTTPException: 429 when Supabase rate-limits sign-ins, 503 for any
            other failure, so neither is reported as a wrong password.
    """
    client: Client = auth_client()
    try:
        result = client.auth.sign_in_with_password(
            {
                "email": str(credentials.email),
                "password": credentials.password,
            }
        )
    except Exception as error:
        status = getattr(error, "status", None)
        if status == 429:
            raise HTTPException(
                429, "Too many sign-ins, try again in a minute."
            ) from error
        if status != 400:
            raise HTTPException(
                503, "Sign-in is unavailable right now. Please try again."
            ) from error
        result = None
    if result is not None and result.session:
        return result.session.access_token, True
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


def optional_login(request: Request) -> Session | None:
    """Identify the student on a public page without requiring a login.

    Args:
        request: Current request, which may carry the login cookie.

    Returns:
        The verified session, or None when signed out, expired, or when
        account services are unavailable, so the public page still loads.
    """
    try:
        return verify_token(request.cookies.get(AUTH_COOKIE, ""))
    except HTTPException:
        return None


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
