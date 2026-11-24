"""Save a student's profile from the HTML form or the JSON profile API."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

import tiger_auth
from models.tiger_profiles import AccountCard, ProfileUpdate
from models.tiger_schedules import UserBase
from models.tiger_session import Session
from routers import tiger_profiles_parsing
from routers.tiger_profiles_parsing import friendly, read_form
from tiger_auth import current_session, require_login
from tiger_views import redirect_to, render_page, valid_token

TOO_LARGE: str = "That PDF is too large (5 MB limit)."
FORM_SLACK: int = 64 * 1024
UNIQUE_VIOLATION: str = "23505"


def show_error(
    request: Request,
    session: Session,
    message: str,
    status: int,
    form: dict[str, str] | None = None,
) -> Response:
    """Redisplay the profile page with a safe error message.

    Args:
        request: Current browser request.
        session: The verified student.
        message: Error shown to the student.
        status: HTTP status code.
        form: What the student typed, kept so they can fix it; None shows
            their saved profile instead.

    Returns:
        The profile page with the student's own data.
    """
    return render_page(
        request,
        "tiger_profile.html",
        profile=tiger_auth.session_card(session),
        form=form,
        error=message,
        saved=False,
        status_code=status,
    )


def draft_profile(
    session: Session, parsed: tiger_profiles_parsing.ParsedTranscript
) -> AccountCard:
    """Merge a parsed transcript onto the student's saved profile for review.

    Args:
        session: The verified student.
        parsed: GPA, credit hours, and courses read from a transcript.

    Returns:
        An AccountCard with the parsed fields ready to show for review;
        nothing is saved to the database yet.
    """
    return tiger_auth.session_card(session).model_copy(
        update={
            "gpa": parsed.gpa,
            "completed_credit_hours": parsed.completed_credit_hours,
            "courses": parsed.courses,
        }
    )


def body_size(request: Request) -> int:
    """Read the declared request size so huge uploads are refused early.

    Args:
        request: Incoming form post.

    Returns:
        The Content-Length in bytes, or 0 when missing or unreadable.
    """
    try:
        return int(request.headers.get("content-length", "0"))
    except ValueError:
        return 0


def save_error(error: Exception) -> tuple[str, int]:
    """Explain why saving the profile failed.

    Args:
        error: The database error.

    Returns:
        A message for the student and the HTTP status: 409 only when the
        username is really taken, otherwise a temporary failure.
    """
    code = str(getattr(error, "code", "") or "")
    if code == UNIQUE_VIOLATION or "duplicate key" in str(error).lower():
        return "That username is already taken. Try another.", 409
    return "Your profile couldn't be saved right now. Please try again.", 503


router: APIRouter = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Display only the verified student's account and saved profile data.

    Args:
        request: Browser request for the profile page.
        session: The verified student whose profile is shown.

    Returns:
        The student's profile page.
    """
    profile: AccountCard = tiger_auth.session_card(session)
    return render_page(
        request,
        "tiger_profile.html",
        profile=profile,
        saved=request.query_params.get("saved") == "1",
    )


@router.post("/profile/transcript", response_class=HTMLResponse)
async def upload_transcript(
    request: Request, session: Session = Depends(require_login)
) -> Response:
    """Read an uploaded transcript PDF and show it for the student to review.

    Args:
        request: Form post carrying the login cookie, form token, and file.
        session: The verified student; signed-out visitors go to login.

    Returns:
        The profile form pre-filled for review, or an error.
    """
    if body_size(request) > tiger_profiles_parsing.MAX_UPLOAD_BYTES + FORM_SLACK:
        return show_error(request, session, TOO_LARGE, 400)
    try:
        form = await request.form(max_files=1, max_fields=2)
    except HTTPException:
        return show_error(
            request, session, "Upload one PDF using the form below.", 400
        )
    if not valid_token(request, form):
        return show_error(
            request, session, "This form expired. Please try again.", 403
        )
    upload = form.get("transcript")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return show_error(
            request, session, "Choose a transcript PDF to upload.", 400
        )
    data = await upload.read(tiger_profiles_parsing.MAX_UPLOAD_BYTES + 1)
    if len(data) > tiger_profiles_parsing.MAX_UPLOAD_BYTES:
        return show_error(request, session, TOO_LARGE, 400)
    try:
        parsed = await run_in_threadpool(tiger_profiles_parsing.parse_upload, data)
    except ValueError as error:
        return show_error(request, session, str(error), 400)
    return render_page(
        request,
        "tiger_profile.html",
        profile=draft_profile(session, parsed),
        draft=True,
        saved=False,
        status_code=200,
    )


@router.post("/profile", response_class=HTMLResponse)
async def save_profile(
    request: Request, session: Session = Depends(require_login)
) -> Response:
    """Save the signed-in student's own profile.

    Args:
        request: Form post carrying the login cookie and form token.
        session: The verified student; signed-out visitors go to login.

    Returns:
        A redirect back to the profile, or the form with an error.
    """
    form = await request.form(max_files=0, max_fields=12)
    data: dict[str, str] = {key: str(value) for key, value in form.items()}
    if not valid_token(request, data):
        return show_error(
            request, session, "This form expired. Please try again.", 403
        )
    try:
        profile = read_form(data)
    except ValueError as error:
        return show_error(request, session, friendly(error), 400, data)
    try:
        await run_in_threadpool(tiger_auth.save_profile, session, profile)
    except Exception as error:
        message, status = save_error(error)
        return show_error(request, session, message, status, data)
    return redirect_to("/profile?saved=1")


@router.get("/api/profile")
def get_profile(session: Session = Depends(current_session)) -> UserBase:
    """Return only the signed-in student's saved profile.

    Args:
        session: The verified student making the request.

    Returns:
        The student's saved profile.
    """
    return tiger_auth.session_profile(session)


@router.put("/api/profile")
def update_profile(
    update: ProfileUpdate, session: Session = Depends(current_session)
) -> UserBase:
    """Save the signed-in student's username, GPA, credit hours, and courses.

    Args:
        update: New profile values.
        session: The verified student making the request.

    Returns:
        The profile as saved.
    """
    username = (update.username or "").strip() or None
    return tiger_auth.save_profile(
        session, update.model_copy(update={"username": username})
    )
