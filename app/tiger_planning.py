"""Parse Planning input and call the shared GPA functions."""

import math

from fastapi import HTTPException
from starlette.datastructures import FormData

import tiger_gpa
from grade_scale import GRADE_POINTS
from models.tiger_planning import (
    CourseRow,
    CumulativeGPARequest,
    GpaCourse,
    PlanningForm,
    PlanningResult,
    RequiredGPARequest,
)

MAX_ROWS: int = 20


def read_form(data: FormData) -> PlanningForm:
    """Keep submitted form values as text for redisplay.

    Args:
        data: HTML form fields, including repeated course fields.

    Returns:
        A form containing the original field text and course rows.
    """
    names: list[str] = [str(value) for value in data.getlist("course_name")]
    credits: list[str] = [str(value) for value in data.getlist("course_credit")]
    grades: list[str] = [str(value) for value in data.getlist("course_grade")]
    row_count: int = max(len(names), len(credits), len(grades), 1)
    rows: list[CourseRow] = []
    for index in range(row_count):
        rows.append(
            CourseRow(
                name=names[index] if index < len(names) else "",
                credit=credits[index] if index < len(credits) else "",
                grade=grades[index] if index < len(grades) else "",
            )
        )
    return PlanningForm(
        current_gpa=str(data.get("current_gpa", "")),
        completed_credits=str(data.get("completed_credits", "")),
        target_gpa=str(data.get("target_gpa", "")),
        rows=rows,
    )


def read_number(value: str, label: str) -> float:
    """Convert a finite numeric field or produce an understandable error.

    Args:
        value: Original field text.
        label: Human-readable field name for the error.

    Returns:
        The finite numeric value.

    Raises:
        ValueError: If the value is blank, nonnumeric, or not finite.
    """
    try:
        number: float = float(value.strip())
    except ValueError as error:
        raise ValueError(f"Enter a number for {label}.") from error
    if not math.isfinite(number):
        raise ValueError(f"Enter a finite number for {label}.")
    return number


def read_credits(value: str, label: str) -> int:
    """Convert a whole-number credit field without truncating decimals.

    Args:
        value: Submitted credit text.
        label: Human-readable field name for the error.

    Returns:
        Whole credit hours; range checks remain in the shared calculations.

    Raises:
        ValueError: If the text is not a whole number.
    """
    try:
        return int(value.strip())
    except ValueError as error:
        raise ValueError(f"Enter whole credit hours for {label}.") from error


def read_courses(rows: list[CourseRow]) -> list[GpaCourse]:
    """Validate nonempty course rows without changing their displayed values.

    Args:
        rows: The original named course rows from the form.

    Returns:
        Courses containing the credit and grade data used by the calculator.

    Raises:
        ValueError: If any partially filled row is incomplete or invalid.
    """
    courses: list[GpaCourse] = []
    for index, row in enumerate(rows, start=1):
        if not any((row.name.strip(), row.credit.strip(), row.grade.strip())):
            continue
        if not row.name.strip() or len(row.name) > 100:
            raise ValueError(
                f"Course {index}: enter a name of 1–100 characters."
            )
        if row.grade not in GRADE_POINTS:
            raise ValueError(
                f"Course {index}: choose an expected letter grade."
            )
        credit: int = read_credits(row.credit, f"course {index}")
        if credit <= 0:
            raise ValueError(
                f"Course {index}: credits must be greater than zero."
            )
        courses.append(GpaCourse(credit=credit, grade=GRADE_POINTS[row.grade]))
    return courses


def calculate_plan(
    form: PlanningForm,
) -> tuple[PlanningResult | None, list[str]]:
    """Calculate the forecast while keeping an unreachable target explainable.

    Args:
        form: Student-entered history, expected courses, and optional target.

    Returns:
        Computed values when possible and any messages to display with the form.
    """
    try:
        current_gpa: float = read_number(form.current_gpa, "current GPA")
        completed_credits: int = read_credits(
            form.completed_credits, "completed credits"
        )
        tiger_gpa.check_history(current_gpa, completed_credits)
        courses: list[GpaCourse] = read_courses(form.rows)
        result: PlanningResult = PlanningResult(
            semester_gpa=tiger_gpa.semester_gpa(courses),
            cumulative_gpa=tiger_gpa.cumulative_gpa(
                CumulativeGPARequest(
                    current_gpa=current_gpa,
                    completed_credits=completed_credits,
                    classes=courses,
                )
            ),
            planned_credits=tiger_gpa.total_credits(courses),
        )
    except ValueError as error:
        return None, [str(error)]
    except HTTPException as error:
        return None, [str(error.detail)]
    if not form.target_gpa.strip():
        return result, []
    try:
        target_gpa: float = read_number(form.target_gpa, "target GPA")
        result.required_gpa = tiger_gpa.required_gpa(
            RequiredGPARequest(
                current_gpa=current_gpa,
                completed_credits=completed_credits,
                planned_credits=result.planned_credits,
                target_gpa=target_gpa,
            )
        )
    except (ValueError, HTTPException) as error:
        result.target_error = (
            str(error.detail)
            if isinstance(error, HTTPException)
            else str(error)
        )
        return result, [result.target_error]
    return result, []
