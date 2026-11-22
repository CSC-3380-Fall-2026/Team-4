"""Save a student's profile from the HTML profile form."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

import tiger_auth
from tiger_views import render_page, valid_token

router: APIRouter = APIRouter()


def parse_courses(text: str) -> list[dict[str, Any]]:
    """Turn lines like "CSC 1350, 4, Computer Science I" into course records.

    Args:
        text: One completed course per line as code, credits, then name.

    Returns:
        Course dictionaries ready to store with the profile.

    Raises:
        ValueError: If a line is incomplete or its credits are invalid.
    """
    courses: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            courses.append(parse_line(line))
    return courses


def parse_line(line: str) -> dict[str, Any]:
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
    if not parts[1].isdigit() or int(parts[1]) > 12:
        raise ValueError(f"Credits must be a whole number: {line.strip()}")
    return {
        "course_code": parts[0][:20],
        "course_name": parts[2][:100],
        "credits": int(parts[1]),
    }


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
    if not text.strip():
        return 0
    if not text.strip().isdigit() or int(text) > 400:
        raise ValueError("Completed credit hours must be a whole number.")
    return int(text)


def read_form(data: dict[str, str]) -> dict[str, Any]:
    """Validate every profile field submitted by the form.

    Args:
        data: Submitted form values.

    Returns:
        Validated profile fields.

    Raises:
        ValueError: With a message for the first invalid field.
    """
    username: str = data.get("username", "").strip()
    if len(username) > 40:
        raise ValueError("Username must be 40 characters or fewer.")
    return {
        "username": username or None,
        "gpa": parse_gpa(data.get("gpa", "")),
        "completed_credit_hours": parse_hours(data.get("hours", "")),
        "courses": parse_courses(data.get("courses", "")),
    }


def show_error(request: Request, message: str, status: int) -> Response:
    """Redisplay the profile page with a safe error message.

    Args:
        request: Current browser request.
        message: Error shown to the student.
        status: HTTP status code.

    Returns:
        The profile page with the student's own saved data.
    """
    try:
        profile = tiger_auth.load_profile(request)
    except HTTPException:
        profile = None
    return render_page(
        request,
        "tiger_profile.html",
        profile=profile,
        error=message,
        saved=False,
        status_code=status,
    )


@router.post("/profile", response_class=HTMLResponse)
async def save_profile(request: Request) -> Response:
    """Save the signed-in student's own profile.

    Args:
        request: Form post carrying the login cookie and form token.

    Returns:
        A redirect back to the profile, or the form with an error.
    """
    form = await request.form(max_files=0, max_fields=12)
    data: dict[str, str] = {key: str(value) for key, value in form.items()}
    if not valid_token(request, data.get("csrf_token", "")):
        return show_error(request, "This form expired. Please try again.", 403)
    try:
        session = tiger_auth.current_session(request, None)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    try:
        fields = read_form(data)
    except ValueError as error:
        return show_error(request, str(error), 400)
    try:
        await run_in_threadpool(tiger_auth.save_profile, session, fields)
    except Exception:
        return show_error(
            request, "That username may already be taken. Try another.", 409
        )
    return RedirectResponse("/profile?saved=1", status_code=303)
