"""Account forms for the browser, and the JSON account API."""

from fastapi import APIRouter, Depends, HTTPException, Request
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
from models.tiger_profiles import AccountCard
from tiger_views import redirect_to, render_page, set_cookie, valid_token

MIN_PASSWORD: int = 8


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


async def signout_page(request: Request) -> RedirectResponse:
    """Clear browser account state and request token revocation when possible.

    Args:
        request: Browser request with an optional access-token cookie.

    Returns:
        A redirect with the account cookie removed.
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
    return tiger_auth.signed_out()


router: APIRouter = APIRouter()
router.add_api_route("/logout", tiger_auth.logout, methods=["POST"])
router.add_api_route("/validateToken", tiger_auth.validate_token, methods=["GET"])


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
    message, accepted = tiger_auth.login(credentials)
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


@router.get("/getUser")
def get_user(
    credentials: HTTPAuthorizationCredentials = Depends(tiger_auth.security),
) -> AccountCard:
    """Return only the profile owned by the verified API caller.

    Args:
        credentials: Bearer token identifying the caller.

    Returns:
        The caller's own account and profile as an AccountCard.
    """
    return tiger_auth.token_profile(credentials.credentials)


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
    response: RedirectResponse = redirect_to("/dashboard")
    set_cookie(response, request, tiger_auth.AUTH_COOKIE, message, 3600)
    return response
