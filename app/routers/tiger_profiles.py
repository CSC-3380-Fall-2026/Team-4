"""Show, read and save a student's profile, from the HTML form or the JSON profile API."""

from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from models.tiger_profiles import (
    AccountCard,
    ProfileCourse,
    ProfileRecord,
)
from models.tiger_schedules import UserBase
from models.tiger_session import Session
from routers import tiger_profiles_parsing, tiger_workday_browser, tiger_workday_parsing
from routers.tiger_profiles_parsing import friendly, read_form
from tiger_auth import require_login
from tiger_views import redirect_to, render_page, valid_token

TOO_LARGE: str = "That PDF is too large (4 MB limit)."
FORM_SLACK: int = 64 * 1024
UNIQUE_VIOLATION: str = "23505"
LINE: set[str] = {"course_code", "course_name", "credits"}


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


def nav_profile(session: Session) -> dict[str, str]:
    """Build the name and email shown at the bottom of the sidebar.

    Args:
        session: The verified student from require_login.

    Returns:
        The saved profile username and the email. The username falls back to
        the account's own when the profile can't be read or has none.
    """
    try:
        saved = profile_row(session, "username").get("username")
    except Exception:
        saved = None
    return {
        "username": str(saved or session.meta.get("username") or ""),
        "email": session.email,
    }


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


def readable_courses(raw: Any) -> list[ProfileCourse]:
    """Keep the saved courses that have the expected shape.

    One malformed entry must not hide the whole profile, or the student
    could never reach the form to fix it.

    Args:
        raw: The profile's stored courses value.

    Returns:
        Valid courses; anything else is skipped.
    """
    courses: list[ProfileCourse] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            courses.append(ProfileCourse.model_validate(item))
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
        username=str(session.meta.get("username") or ""),
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
                    "courses": readable_courses(saved.get("courses")),
                }
            )
    except Exception:
        card = card.model_copy(update={"data_error": True})
    return card


def write_profile(session: Session, profile: ProfileRecord) -> UserBase:
    """Store validated profile fields for the session's own student.

    Args:
        session: The verified student and their database client.
        profile: Username, GPA, credit hours, and courses to save.

    Returns:
        The profile as saved.
    """
    row: dict[str, Any] = {
        **profile.model_dump(include=set(ProfileRecord.model_fields)),
        # Courses without a term or grade are stored as before, without the keys.
        "courses": [course.model_dump(exclude_none=True) for course in profile.courses],
        "id": session.user_id,
        "email": session.email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.db.table("profiles").upsert(row).execute()
    return session_profile(session)


def with_terms(session: Session, profile: ProfileRecord) -> ProfileRecord:
    """Keep saved terms and grades on courses submitted through the form.

    The form has no term or grade fields, so each submitted course takes
    them from a saved course: the same line if it is unchanged, else the
    first with the same code. Each saved course is used once.

    Args:
        session: The verified student.
        profile: The profile read from the form.

    Returns:
        The profile with terms and grades copied over.
    """
    left = readable_courses(profile_row(session, "courses").get("courses"))
    courses: list[ProfileCourse] = []
    for course in profile.courses:
        line = course.model_dump(include=LINE)
        same_line = [old for old in left if old.model_dump(include=LINE) == line]
        same_code = [old for old in left if old.course_code == course.course_code]
        match = (same_line or same_code or [None])[0]
        if match:
            left.remove(match)
            course = course.model_copy(update={"term": match.term, "grade": match.grade})
        courses.append(course)
    return profile.model_copy(update={"courses": courses})


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
        profile=session_card(session),
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
    return session_card(session).model_copy(
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
    profile: AccountCard = session_card(session)
    return render_page(
        request,
        "tiger_profile.html",
        profile=profile,
        saved=request.query_params.get("saved") == "1",
        workday=tiger_workday_browser.sync_status(session),
        term_gpas=tiger_workday_parsing.term_gpas(profile.courses),
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
        await run_in_threadpool(
            lambda: write_profile(session, with_terms(session, profile))
        )
    except Exception as error:
        message, status = save_error(error)
        return show_error(request, session, message, status, data)
    return redirect_to("/profile?saved=1")

