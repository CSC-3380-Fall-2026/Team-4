"""Account forms for the browser, and the JSON account API."""

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

import tiger_auth
from models.tiger_accounts import (
    SignupResponse,
    TokenResponse,
    UserAuthSchema,
)
from tiger_views import redirect_to, render_page, valid_token

MIN_PASSWORD: int = 8
# Friends search for this exact name, so keep it plain.
USERNAME: re.Pattern[str] = re.compile(r"[A-Za-z0-9_]{3,40}")
BAD_USERNAME: str = "Choose a username of 3 to 40 letters, numbers, or underscores."
TAKEN: str = "That username is already taken. Try another."


def account_page(
    request: Request,
    mode: str,
    email: str = "",
    error: str = "",
    message: str = "",
    status_code: int = 200,
    **typed: str,
) -> HTMLResponse:
    """Render an account form without ever redisplaying a submitted password.

    Args:
        request: Current browser request.
        mode: Either login or signup.
        email: Submitted email to preserve after validation.
        error: Safe error message for the student.
        message: Success message after a registration request.
        status_code: HTTP response status.
        typed: Other submitted fields to redisplay: username and full_name.

    Returns:
        The account form in William's shared layout.
    """
    template_name: str = (
        "tiger_login.html" if mode == "login" else "tiger_signin.html"
    )
    return render_page(
        request,
        template_name,
        mode=mode,
        email=email,
        error=error,
        message=message,
        status_code=status_code,
        **typed,
    )


async def signout_page(request: Request) -> RedirectResponse:
    """Clear browser account state and request token revocation when possible.

    After the access cookie's hour is up, the refresh cookie is renewed
    first so Supabase still revokes the session.

    Args:
        request: Browser request with optional access and refresh cookies.

    Returns:
        A redirect with the login cookies removed, even if Supabase fails.
    """
    token: str = request.cookies.get(tiger_auth.AUTH_COOKIE, "")
    try:
        if not token:
            session = await run_in_threadpool(tiger_auth.refreshed, request)
            # Revoked below, so never stored in the cookies.
            request.state.tokens = None
            token = session.token if session else ""
        if token:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            )
            await run_in_threadpool(tiger_auth.logout, credentials)
    except HTTPException:
        pass
    return tiger_auth.signed_out()


async def submit_signup(
    request: Request, data: FormData, credentials: UserAuthSchema
) -> Response:
    """Check the chosen username, then register with it in user metadata.

    Args:
        request: Submitted signup form.
        data: Its fields, including username and full_name.
        credentials: The already validated email and password.

    Returns:
        The signup page with a confirmation or an error.
    """
    email: str = str(credentials.email)
    username: str = str(data.get("username", "")).strip()
    full_name: str = " ".join(str(data.get("full_name", "")).split())[:80]
    typed: dict[str, str] = {"username": username, "full_name": full_name}
    if not USERNAME.fullmatch(username):
        return account_page(
            request, "signup", email, error=BAD_USERNAME, status_code=400, **typed
        )
    try:
        if await run_in_threadpool(tiger_auth.username_taken, username):
            return account_page(
                request, "signup", email, error=TAKEN, status_code=409, **typed
            )
        message, accepted = await run_in_threadpool(
            tiger_auth.signup, credentials, username, full_name
        )
    except HTTPException as error:
        return account_page(
            request,
            "signup",
            email,
            error=str(error.detail),
            status_code=error.status_code,
            **typed,
        )
    if not accepted:
        return account_page(
            request, "signup", email, error=message, status_code=400, **typed
        )
    return account_page(request, "signup", email, message=message)


router: APIRouter = APIRouter()
router.add_api_route("/logout", tiger_auth.logout, methods=["POST"])


@router.post("/login")
def login_api(credentials: UserAuthSchema) -> TokenResponse:
    """Sign in through the JSON API.

    Args:
        credentials: Student email and password.

    Returns:
        The access token and its type, as a TokenResponse.

    Raises:
        HTTPException: 401 when the email or password is wrong.
    """
    message, accepted, _ = tiger_auth.login(credentials)
    if not accepted:
        raise HTTPException(401, message)
    return TokenResponse(access_token=message)


@router.post("/signup")
def signup_api(credentials: UserAuthSchema) -> SignupResponse:
    """Register through the JSON API.

    Args:
        credentials: Student email and chosen password.

    Returns:
        A SignupResponse confirming the account was requested, with next steps.

    Raises:
        HTTPException: 400 when registration is refused.
    """
    message, accepted = tiger_auth.signup(credentials)
    if not accepted:
        raise HTTPException(400, message)
    return SignupResponse(created=True, message=message)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Open the login page.

    Args:
        request: Browser request for login.

    Returns:
        The empty login form.
    """
    return account_page(request, "login")


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request) -> HTMLResponse:
    """Open the signup page.

    Args:
        request: Browser request for registration.

    Returns:
        The empty signup form.
    """
    return account_page(request, "signup")


@router.get("/signin")
def signin_page(request: Request) -> RedirectResponse:
    """Preserve the old registration-page address.

    Args:
        request: Browser request for the previous signin URL.

    Returns:
        A redirect to the consistently named signup page.
    """
    return RedirectResponse("/signup", status_code=303)


@router.post("/account/{mode}", response_class=HTMLResponse)
async def submit_account(request: Request, mode: str) -> Response:
    """Validate an HTML account form and reuse the existing account operations.

    Args:
        request: Submitted form containing email, password, and form token.
        mode: Login, signup, or logout operation.

    Returns:
        A useful form response or a redirect after successful login/logout.

    Raises:
        HTTPException: 404 for an unknown account action.
    """
    if mode not in ("login", "signup", "logout"):
        raise HTTPException(404, "Account action not found.")
    data: FormData = await request.form(max_files=0, max_fields=8)
    email: str = str(data.get("email", "")).strip()
    if not valid_token(request, data):
        return account_page(
            request,
            "login" if mode == "logout" else mode,
            email,
            error="This form expired. Please try again.",
            status_code=403,
        )
    if mode == "logout":
        return await signout_page(request)
    password: str = str(data.get("password", ""))
    if not password or len(password) > 1024:
        return account_page(
            request,
            mode,
            email,
            error="Enter a valid password.",
            status_code=400,
        )
    if mode == "signup" and len(password) < MIN_PASSWORD:
        return account_page(
            request,
            mode,
            email,
            error=f"Password must be at least {MIN_PASSWORD} characters.",
            status_code=400,
        )
    if mode == "signup" and password != str(data.get("confirm_password", "")):
        return account_page(
            request, mode, email, error="Passwords must match.", status_code=400
        )
    try:
        credentials: UserAuthSchema = UserAuthSchema(
            email=email, password=password
        )
    except ValidationError:
        return account_page(
            request,
            mode,
            email,
            error="Enter a valid email address.",
            status_code=400,
        )
    if mode == "signup":
        return await submit_signup(request, data, credentials)
    try:
        message, accepted, refresh = await run_in_threadpool(
            tiger_auth.login, credentials
        )
    except HTTPException as error:
        return account_page(
            request,
            mode,
            email,
            error=str(error.detail),
            status_code=error.status_code,
        )
    if not accepted:
        return account_page(
            request, mode, email, error=message, status_code=400
        )
    response: RedirectResponse = redirect_to("/dashboard")
    remember = bool(data.get("remember"))
    tiger_auth.store_tokens(response, request, message, refresh, remember)
    return response
