"""Keep account APIs available without requiring credentials at app startup."""

import logging
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, ClientOptions, create_client

from tiger_views import redirect_to, set_cookie

from models.tiger_accounts import UserAuthSchema
from models.tiger_session import Session

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")
security: HTTPBearer = HTTPBearer()
optional_security: HTTPBearer = HTTPBearer(auto_error=False)
AUTH_COOKIE: str = "tiger_access"
REFRESH_COOKIE: str = "tiger_refresh"
REFRESH_AGE: int = 30 * 24 * 3600
# Set only for "Keep me logged in", so a renewal keeps the student's choice.
REMEMBER_COOKIE: str = "tiger_remember"
LOG: logging.Logger = logging.getLogger(__name__)


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


def login(credentials: UserAuthSchema) -> tuple[str, bool, str]:
    """Sign in with Supabase for the HTML login form.

    Args:
        credentials: Student email and password.

    Returns:
        The access token, True and the refresh token on success, or a safe
        message, False and "" when Supabase refused the email or password.

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
        meta: dict[str, Any] = getattr(result.user, "user_metadata", None) or {}
        claim_username(
            result.session.access_token,
            result.user.id,
            str(meta.get("username") or ""),
        )
        return result.session.access_token, True, result.session.refresh_token
    return (
        "Check your email and password, and confirm your email if required.",
        False,
        "",
    )


def signup(
    credentials: UserAuthSchema, username: str = "", full_name: str = ""
) -> tuple[str, bool]:
    """Request account registration with Supabase for the HTML signup form.

    Args:
        credentials: Student email and chosen password.
        username: Username friends will search for, kept in user metadata.
        full_name: The student's name, kept in user metadata.

    Returns:
        A confirmation message and whether the request was accepted.
    """
    client: Client = auth_client()
    meta: dict[str, str] = {"username": username, "full_name": full_name}
    try:
        result = client.auth.sign_up(
            {
                "email": str(credentials.email),
                "password": credentials.password,
                "options": {"data": {k: v for k, v in meta.items() if v}},
            }
        )
    except Exception:
        result = None
    if result is None or not result.user:
        return (
            "Registration could not be completed. "
            "Try logging in or try again later.",
            False,
        )
    if not result.session:
        return "Check your email for confirmation, then log in.", True
    claim_username(result.session.access_token, result.user.id, username)
    return "Your account is ready. Log in to continue.", True


def username_taken(username: str) -> bool:
    """Ask the database whether another student already has a username.

    Args:
        username: Username to check, ignoring case.

    Returns:
        True when taken; False when free or when the check is unavailable
        (before database/tiger_setup.sql adds it), leaving the unique
        index as the last guard.
    """
    try:
        found = auth_client().rpc("username_taken", {"name": username}).execute()
    except Exception:
        LOG.warning("username_taken() unavailable; re-run tiger_setup.sql.")
        return False
    return found.data is True


def claim_username(token: str, user_id: str, username: str) -> None:
    """Copy the signup username onto the student's profile if it has none.

    The profile trigger in database/tiger_setup.sql copies it at signup;
    this covers databases still running the older trigger.

    Args:
        token: The student's access token.
        user_id: The student's id.
        username: Username from their signup metadata; empty does nothing.
    """
    if not username:
        return
    try:
        (
            user_client(token)
            .table("profiles")
            .update({"username": username})
            .eq("id", user_id)
            .is_("username", "null")
            .execute()
        )
    except Exception:
        # Taken meanwhile, or no profile row: the student sets it on Profile.
        LOG.warning("Could not save the signup username.", exc_info=True)


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


def raise_outage(error: Exception) -> None:
    """Tell a refused token apart from Supabase being unreachable.

    Args:
        error: What the Supabase auth call raised.

    Raises:
        HTTPException: 503 unless Supabase refused the token with 400, 401
            or 403, so an outage never signs the student out.
    """
    if getattr(error, "status", None) not in (400, 401, 403):
        raise HTTPException(
            503, "Account services are temporarily unavailable."
        ) from error


def verify_token(token: str) -> Session | None:
    """Ask Supabase to verify an access token's signature and expiry.

    Args:
        token: Access token from a cookie or bearer header.

    Returns:
        The verified session, or None for a missing, invalid or expired token.

    Raises:
        HTTPException: 503 if account services are unavailable.
    """
    if not token:
        return None
    try:
        result = auth_client().auth.get_user(token)
    except HTTPException:
        raise
    except Exception as error:
        raise_outage(error)
        return None
    user = result.user if result is not None else None
    if user is None:
        return None
    meta: dict[str, Any] = getattr(user, "user_metadata", None) or {}
    return Session(user.id, user.email or "", token, user_client(token), meta)


def store_tokens(
    response: Response, request: Request, access: str, refresh: str, remember: bool
) -> None:
    """Put the tokens in the login cookies.

    Args:
        response: Response that carries the cookies.
        request: Current request, used to detect HTTPS.
        access: Access token, kept for an hour.
        refresh: Refresh token, kept 30 days when remembered, else until
            the browser closes.
        remember: Whether the student ticked "Keep me logged in".
    """
    age: int | None = REFRESH_AGE if remember else None
    set_cookie(response, request, AUTH_COOKIE, access, 3600)
    set_cookie(response, request, REFRESH_COOKIE, refresh, age)
    if remember:
        set_cookie(response, request, REMEMBER_COOKIE, "1", age)
    else:
        response.delete_cookie(REMEMBER_COOKIE)


def refreshed(request: Request) -> Session | None:
    """Renew an expired browser session with the refresh-token cookie.

    The new tokens are left on request.state for tiger_app to store in
    the response cookies.

    Args:
        request: Current request, which may carry the refresh cookie.

    Returns:
        The renewed session, or None without a cookie or when Supabase
        refuses it.

    Raises:
        HTTPException: If account services are unavailable.
    """
    token: str = request.cookies.get(REFRESH_COOKIE, "")
    if not token:
        return None
    try:
        result = auth_client().auth.refresh_session(token)
    except HTTPException:
        raise
    except Exception as error:
        raise_outage(error)
        return None
    if result is None or not result.session or not result.user:
        return None
    access: str = result.session.access_token
    request.state.tokens = (access, result.session.refresh_token)
    meta: dict[str, Any] = getattr(result.user, "user_metadata", None) or {}
    return Session(
        result.user.id, result.user.email or "", access, user_client(access), meta
    )


def cookie_session(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> Session | None:
    """Verify the bearer token or login cookie, renewing an expired cookie.

    Args:
        request: Current request.
        credentials: Optional bearer token; API callers renew their own.

    Returns:
        The verified session, or None when signed out.

    Raises:
        HTTPException: If account services are unavailable.
    """
    session: Session | None = verify_token(request_token(request, credentials))
    if session is None and credentials is None:
        session = refreshed(request)
    return session


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
    session: Session | None = cookie_session(request, credentials)
    if session is not None:
        return session
    if not request_token(request, credentials):
        raise HTTPException(401, "Not signed in.")
    raise HTTPException(401, "Session expired, please log in again.")


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
    session: Session | None = cookie_session(request, credentials)
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
        return cookie_session(request, None)
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
    """Send the browser to /login with its login cookies removed.

    Returns:
        An uncached 303 redirect to /login that deletes the login cookies.
    """
    response: RedirectResponse = redirect_to("/login")
    response.delete_cookie(AUTH_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)
    response.delete_cookie(REMEMBER_COOKIE)
    return response
