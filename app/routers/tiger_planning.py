"""Serve the Planning form using Python and ordinary HTML submissions."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from grade_scale import GRADE_POINTS
from models.tiger_planning import CourseRow, PlanningForm, PlanningResult
from tiger_forecast import save_forecast
from tiger_planning import MAX_ROWS, calculate_plan, read_form
from tiger_views import render_page, valid_token

router: APIRouter = APIRouter()


@router.get("/planning", response_class=HTMLResponse)
def planning_page(request: Request, example: bool = False) -> HTMLResponse:
    """Open a blank plan or the explicitly requested acceptance-test example.

    Args:
        request: Browser request for the Planning page.
        example: Whether to load the labeled 60-credit / 15-credit example.

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


@router.post("/planning", response_class=HTMLResponse)
async def submit_plan(request: Request) -> HTMLResponse:
    """Process row edits or calculate a forecast without losing input values.

    Args:
        request: Submitted Planning form, including repeated course rows.

    Returns:
        The same form with its entered values, results, or readable errors.
    """
    data: FormData = await request.form(max_files=0, max_fields=100)
    form: PlanningForm = read_form(data)
    action: str = str(data.get("action", "calculate"))
    result: PlanningResult | None = None
    errors: list[str] = []
    status_code: int = 200
    if not valid_token(request, str(data.get("csrf_token", ""))):
        errors = [
            "This form expired. Your entries are kept; please submit again."
        ]
        status_code = 403
    elif any(
        len(data.getlist(key)) > MAX_ROWS
        for key in ("course_name", "course_credit", "course_grade")
    ):
        errors = [f"Use no more than {MAX_ROWS} courses in one plan."]
        status_code = 400
    elif action == "add":
        if len(form.rows) < MAX_ROWS:
            form.rows.append(CourseRow())
        else:
            errors = [f"You can plan up to {MAX_ROWS} courses."]
            status_code = 400
    elif action.startswith("remove:"):
        index: str = action.removeprefix("remove:")
        if index.isdigit() and int(index) < len(form.rows):
            form.rows.pop(int(index))
            if not form.rows:
                form.rows.append(CourseRow())
        else:
            errors = ["Choose an existing course row to remove."]
            status_code = 400
    elif action == "calculate":
        result, errors = calculate_plan(form)
        status_code = 400 if errors else 200
    else:
        errors = ["Choose Calculate GPA, Add course, or Remove."]
        status_code = 400
    response: HTMLResponse = render_page(
        request,
        "tiger_planner.html",
        status_code=status_code,
        form=form,
        result=result,
        errors=errors,
        grades=GRADE_POINTS,
        max_rows=MAX_ROWS,
        example=False,
    )
    if result is not None:
        save_forecast(request, response, result)
    return response
