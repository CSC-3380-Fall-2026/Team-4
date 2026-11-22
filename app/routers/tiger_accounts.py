"""Connect HTML account forms to the team's existing account operations."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

import tiger_auth
from tiger_forecast import COOKIE_NAME
from tiger_models import UserAuthSchema
from tiger_views import render_page, valid_token

router: APIRouter = APIRouter()


def account_page(
    request: Request,
    mode: str,
    email: str = "",
    error: str = "",
    message: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    """Render an account form without ever redisplaying a submitted password.

    Args:
        request: Current browser request.
        mode: Either login or signup.
        email: Submitted email to preserve after validation.
        error: Safe error message for the student.
        message: Success message after a registration request.
        status_code: HTTP response status.

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
    )


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
    """
    if mode not in ("login", "signup", "logout"):
        raise HTTPException(404, "Account action not found.")
    data: FormData = await request.form(max_files=0, max_fields=8)
    email: str = str(data.get("email", "")).strip()
    if not valid_token(request, str(data.get("csrf_token", ""))):
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
    try:
        operation = tiger_auth.login if mode == "login" else tiger_auth.signup
        message, accepted = await run_in_threadpool(operation, credentials)
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
    if mode == "signup":
        return account_page(request, mode, email, message=message)
    response: RedirectResponse = RedirectResponse("/profile", status_code=303)
    response.set_cookie(
        tiger_auth.AUTH_COOKIE,
        message,
        max_age=3600,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    response.delete_cookie(COOKIE_NAME)
    response.headers["Cache-Control"] = "no-store"
    return response


async def signout_page(request: Request) -> RedirectResponse:
    """Clear browser account state and request token revocation when possible.

    Args:
        request: Browser request with an optional access-token cookie.

    Returns:
        A redirect with account and forecast cookies removed.
    """
    token: str = request.cookies.get(tiger_auth.AUTH_COOKIE, "")
    if token:
        try:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            )
            await run_in_threadpool(tiger_auth.logout, credentials)
        except HTTPException:
            pass
    response: RedirectResponse = RedirectResponse("/login", status_code=303)
    response.delete_cookie(tiger_auth.AUTH_COOKIE)
    response.delete_cookie(COOKIE_NAME)
    response.headers["Cache-Control"] = "no-store"
    return response
