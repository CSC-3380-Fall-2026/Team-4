"""Serve the Planning form using Python and ordinary HTML submissions."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from grade_scale import GRADE_POINTS
from models.tiger_planning import CourseRow, PlanningForm, PlanningResult
from tiger_auth import Session, require_login
from tiger_forecast import save_forecast
from tiger_planning import MAX_ROWS, calculate_plan, read_form
from tiger_views import render_page, valid_token

router: APIRouter = APIRouter()


@router.get("/planning", response_class=HTMLResponse)
def planning_page(
    request: Request,
    example: bool = False,
    session: Session = Depends(require_login),
) -> HTMLResponse:
    """Open a blank plan or the explicitly requested acceptance-test example.

    Args:
        request: Browser request for the Planning page.
        example: Whether to load the labeled 60-credit / 15-credit example.
        session: The verified student; signed-out visitors go to login.

    Returns:
        A Planning form with no fabricated calculation results.
    """
    form: PlanningForm = PlanningForm(rows=[CourseRow() for _ in range(3)])
    if example:
        form = PlanningForm(
            current_gpa="3.0",
            completed_credits="60",
            target_gpa="3.20",
            rows=[
                CourseRow(name, "3", "A")
                for name in (
                    "CSC 2259",
                    "CSC 2262",
                    "CSC 3102",
                    "CSC 3380",
                    "CSC 3501",
                )
            ],
        )
    return render_page(
        request,
        "tiger_planner.html",
        form=form,
        result=None,
        errors=[],
        grades=GRADE_POINTS,
        max_rows=MAX_ROWS,
        example=example,
    )


def edit_rows(form: PlanningForm, action: str) -> tuple[list[str], int]:
    """Apply an add-row or remove-row action to the form.

    Args:
        form: Planning form whose rows are edited in place.
        action: The submitted "add" or "remove:<index>" action.

    Returns:
        Any error messages and the HTTP status code.
    """
    if action == "add":
        if len(form.rows) < MAX_ROWS:
            form.rows.append(CourseRow())
            return [], 200
        return [f"You can plan up to {MAX_ROWS} courses."], 400
    index: str = action.removeprefix("remove:")
    if not (index.isdigit() and int(index) < len(form.rows)):
        return ["Choose an existing course row to remove."], 400
    form.rows.pop(int(index))
    if not form.rows:
        form.rows.append(CourseRow())
    return [], 200


def run_action(
    form: PlanningForm, action: str
) -> tuple[PlanningResult | None, list[str], int]:
    """Carry out a validated form action.

    Args:
        form: Planning form to edit or calculate.
        action: The submitted action name.

    Returns:
        The result (if calculated), error messages, and status code.
    """
    if action == "add" or action.startswith("remove:"):
        errors, status = edit_rows(form, action)
        return None, errors, status
    if action == "calculate":
        result, errors = calculate_plan(form)
        return result, errors, 400 if errors else 200
    return None, ["Choose Calculate GPA, Add course, or Remove."], 400


def check_form(request: Request, data: FormData) -> tuple[list[str], int]:
    """Validate the CSRF token and row counts of a submission.

    Args:
        request: The submitted request.
        data: Parsed form data.

    Returns:
        Error messages and status code; empty errors with 200 if valid.
    """
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


@router.post("/planning", response_class=HTMLResponse)
async def submit_plan(
    request: Request, session: Session = Depends(require_login)
) -> HTMLResponse:
    """Process row edits or calculate a forecast without losing input values.

    Args:
        request: Submitted Planning form, including repeated course rows.
        session: The verified student whose forecast is saved.

    Returns:
        The same form with its entered values, results, or readable errors.
    """
    data: FormData = await request.form(max_files=0, max_fields=100)
    form: PlanningForm = read_form(data)
    action: str = str(data.get("action", "calculate"))
    result: PlanningResult | None = None
    errors, status_code = check_form(request, data)
    if not errors:
        result, errors, status_code = run_action(form, action)
    unsaved: bool = result is not None and not await run_in_threadpool(
        save_forecast, session, result
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
        example=False,
        unsaved=unsaved,
    )
