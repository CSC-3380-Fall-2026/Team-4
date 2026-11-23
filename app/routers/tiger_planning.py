"""Serve GPA planning with saved account data and student-entered grades."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

import tiger_auth
from grade_scale import GRADE_POINTS
from models.tiger_planning import CourseRow, PlanningForm, PlanningResult
from tiger_auth import Session, require_login
from tiger_forecast import save_forecast
from tiger_models import Classes, Schedule
from tiger_planning import MAX_ROWS, calculate_plan, read_form
from tiger_schedule_store import fetch_schedule, list_schedules
from tiger_views import render_page, valid_token

router: APIRouter = APIRouter()


def saved_start(session: Session) -> tuple[PlanningForm, str]:
    """Read the student's saved GPA and completed GPA credits."""
    form = PlanningForm(rows=[CourseRow()])
    try:
        profile = tiger_auth.session_profile(session)
    except Exception:
        return form, (
            "Your saved academic record could not be loaded. "
            "You can enter your GPA and credits below."
        )

    if profile.gpa is not None:
        form.current_gpa = f"{profile.gpa:.2f}"
    form.completed_credits = str(profile.completed_credit_hours)
    return form, ""


def schedule_options(session: Session) -> tuple[list[Schedule], str]:
    """Read schedules owned by the signed-in student."""
    try:
        return list_schedules(session), ""
    except Exception:
        return [], (
            "Saved schedules could not be loaded. "
            "You can still enter courses manually."
        )


def load_schedule(
    form: PlanningForm, session: Session, schedule_id: str
) -> tuple[list[str], int]:
    """Load real course names and credits without assigning expected grades."""
    if not schedule_id or len(schedule_id) > 100:
        return ["Choose a saved schedule."], 400

    try:
        schedule = fetch_schedule(session, schedule_id)
    except HTTPException as error:
        return [str(error.detail)], error.status_code
    except Exception:
        return ["Your saved courses could not be loaded. Try again."], 503

    if schedule._kept.get("sections"):
        return [
            "Some courses in this schedule could not be read. "
            "Review the schedule before loading its courses."
        ], 409

    courses = [
        event for event in schedule.events if isinstance(event, Classes)
    ]
    if not courses:
        return ["This schedule has no courses. Add courses in Schedule first."], 400
    if len(courses) > MAX_ROWS:
        return [f"This schedule exceeds the limit of {MAX_ROWS} courses."], 400

    seen: set[tuple[str, int, str]] = set()
    for course in courses:
        key = (
            course.department.strip().upper(),
            course.number,
            course.semester.strip().casefold(),
        )
        if key in seen:
            return [
                "This schedule contains multiple entries for the same course. "
                "Enter each course once in the planner so its credits are "
                "counted correctly. Your current entries have been kept."
            ], 409
        seen.add(key)

    form.rows = [
        CourseRow(name=course.title, credit=str(course.credit), grade="")
        for course in courses
    ]
    return [], 200


def edit_rows(form: PlanningForm, action: str) -> tuple[list[str], int]:
    """Add or remove a course row while preserving the remaining inputs."""
    if action == "add":
        if len(form.rows) >= MAX_ROWS:
            return [f"You can plan up to {MAX_ROWS} courses."], 400
        form.rows.append(CourseRow())
        return [], 200

    index = action.removeprefix("remove:")
    if not (
        index.isascii()
        and index.isdigit()
        and len(index) <= len(str(MAX_ROWS))
    ):
        return ["Choose an existing course row to remove."], 400

    number = int(index)
    if number >= len(form.rows):
        return ["Choose an existing course row to remove."], 400

    form.rows.pop(number)
    if not form.rows:
        form.rows.append(CourseRow())
    return [], 200


def run_action(
    form: PlanningForm, action: str
) -> tuple[PlanningResult | None, list[str], int]:
    """Edit rows or use the existing GPA calculation functions."""
    if action == "add" or action.startswith("remove:"):
        errors, status = edit_rows(form, action)
        return None, errors, status

    if action == "calculate":
        result, errors = calculate_plan(form)
        return result, errors, 400 if errors else 200

    return None, ["Choose an available planning action."], 400


def check_form(request: Request, data: FormData) -> tuple[list[str], int]:
    """Validate the form token and maximum number of course rows."""
    if not valid_token(request, str(data.get("csrf_token", ""))):
        return [
            "This form expired. Your entries are kept; please submit again."
        ], 403

    if any(
        len(data.getlist(key)) > MAX_ROWS
        for key in ("course_name", "course_credit", "course_grade")
    ):
        return [f"Use no more than {MAX_ROWS} courses in one plan."], 400

    return [], 200


@router.get("/planning", response_class=HTMLResponse)
def planning_page(
    request: Request,
    session: Session = Depends(require_login),
) -> HTMLResponse:
    """Open Planning with saved account totals and blank course inputs."""
    form, profile_error = saved_start(session)
    schedules, schedule_error = schedule_options(session)

    return render_page(
        request,
        "tiger_planner.html",
        form=form,
        result=None,
        errors=[],
        grades=GRADE_POINTS,
        max_rows=MAX_ROWS,
        schedules=schedules,
        schedule_id="",
        schedule_error=schedule_error,
        profile_error=profile_error,
        unsaved=False,
        loaded=False,
    )


@router.post("/planning", response_class=HTMLResponse)
async def submit_plan(
    request: Request,
    session: Session = Depends(require_login),
) -> HTMLResponse:
    """Load courses, edit rows, or calculate and save a GPA forecast."""
    data = await request.form(max_files=0, max_fields=100)
    form = read_form(data)
    action = str(data.get("action", "calculate"))
    schedule_id = str(data.get("schedule_id", "")).strip()

    result: PlanningResult | None = None
    loaded = False
    unsaved = False
    errors, status_code = check_form(request, data)

    if not errors:
        if action == "load_schedule":
            errors, status_code = await run_in_threadpool(
                load_schedule, form, session, schedule_id
            )
            loaded = not errors
        else:
            result, errors, status_code = run_action(form, action)

    if result is not None:
        unsaved = not await run_in_threadpool(
            save_forecast, session, result
        )

    schedules, schedule_error = await run_in_threadpool(
        schedule_options, session
    )

    return render_page(
        request,
        "tiger_planner.html",
        status_code=status_code,
        form=form,
        result=result,
        errors=errors,
        grades=GRADE_POINTS,
        max_rows=MAX_ROWS,
        schedules=schedules,
        schedule_id=schedule_id,
        schedule_error=schedule_error,
        profile_error="",
        unsaved=unsaved,
        loaded=loaded,
    )
