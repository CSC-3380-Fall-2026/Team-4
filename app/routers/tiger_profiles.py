"""Save a student's profile from the HTML form or the JSON profile API."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

import tiger_auth
import tiger_transcript
from models.tiger_profile import (
    AccountCard,
    ProfileCourse,
    ProfileRecord,
    ProfileUpdate,
)
from models.tiger_schedule import UserBase
from models.tiger_session import Session
from tiger_auth import current_session, require_login
from tiger_views import redirect_to, render_page, valid_token

router: APIRouter = APIRouter()
TOO_LARGE: str = "That PDF is too large (5 MB limit)."
FORM_SLACK: int = 64 * 1024
UNIQUE_VIOLATION: str = "23505"


def whole_number(text: str) -> bool:
    """Tell whether text is a plain ASCII whole number.

    str.isdigit() alone also accepts characters such as "²" that int()
    cannot read.

    Args:
        text: Text to check.

    Returns:
        True for text made only of the digits 0-9.
    """
    return text.isascii() and text.isdigit()


def parse_courses(text: str) -> list[ProfileCourse]:
    """Turn lines like "CSC 1350, 4, Computer Science I" into course records.

    Args:
        text: One completed course per line as code, credits, then name.

    Returns:
        Course records ready to store with the profile.

    Raises:
        ValueError: If a line is incomplete or its credits are invalid.
    """
    courses: list[ProfileCourse] = []
    for line in text.splitlines():
        if line.strip():
            courses.append(parse_line(line))
    return courses


def parse_line(line: str) -> ProfileCourse:
    """Read one completed-course line.

    Args:
        line: Text formatted as code, credits, name.

    Returns:
        One course record.

    Raises:
        ValueError: If the line is incomplete or its credits are invalid.
    """
    parts: list[str] = [part.strip() for part in line.split(",", 2)]
    if len(parts) < 3 or not parts[0] or not parts[2]:
        raise ValueError(f"Use code, credits, name on each line: {line.strip()}")
    if not whole_number(parts[1]) or int(parts[1]) > 12:
        raise ValueError(f"Credits must be a whole number: {line.strip()}")
    return ProfileCourse(
        course_code=parts[0][:20],
        course_name=parts[2][:100],
        credits=int(parts[1]),
    )


def parse_gpa(text: str) -> float | None:
    """Read an optional GPA between 0.0 and 4.3.

    Args:
        text: Raw GPA text from the form.

    Returns:
        The GPA, or None when left blank.

    Raises:
        ValueError: If the text is not a valid GPA.
    """
    if not text.strip():
        return None
    value: float = float(text)
    if not 0 <= value <= 4.3:
        raise ValueError("GPA must be between 0.0 and 4.3.")
    return round(value, 2)


def parse_hours(text: str) -> int:
    """Read completed GPA credit hours.

    Args:
        text: Raw credit-hour text from the form.

    Returns:
        A whole number of hours, or 0 when left blank.

    Raises:
        ValueError: If the text is not a non-negative whole number.
    """
    value = text.strip()
    if not value:
        return 0
    if not whole_number(value) or int(value) > 400:
        raise ValueError("Completed credit hours must be a whole number.")
    return int(value)


def read_form(data: dict[str, str]) -> ProfileRecord:
    """Validate every profile field submitted by the form.

    Args:
        data: Submitted form values.

    Returns:
        The validated profile.

    Raises:
        ValueError: With a message for the first invalid field.
    """
    username: str = data.get("username", "").strip()
    if len(username) > 40:
        raise ValueError("Username must be 40 characters or fewer.")
    return ProfileRecord(
        username=username or None,
        gpa=parse_gpa(data.get("gpa", "")),
        completed_credit_hours=parse_hours(data.get("hours", "")),
        courses=parse_courses(data.get("courses", "")),
    )


def friendly(error: ValueError) -> str:
    """Turn a form validation error into a message for the student.

    Args:
        error: The validation error.

    Returns:
        A readable message; Python's own float errors are replaced.
    """
    text = str(error)
    if text.startswith("could not convert"):
        return "GPA must be a number between 0.0 and 4.3."
    return text


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
    session: Session, parsed: tiger_transcript.ParsedTranscript
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
    if body_size(request) > tiger_transcript.MAX_UPLOAD_BYTES + FORM_SLACK:
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
    data = await upload.read(tiger_transcript.MAX_UPLOAD_BYTES + 1)
    if len(data) > tiger_transcript.MAX_UPLOAD_BYTES:
        return show_error(request, session, TOO_LARGE, 400)
    try:
        parsed = await run_in_threadpool(tiger_transcript.parse_upload, data)
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
