"""Calculate GPA with the existing formulas, and parse Planning input for them."""

import math

from fastapi import HTTPException
from starlette.datastructures import FormData

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
MAX_GPA: float = 4.3


def check_history(current_gpa: float, completed_credits: int) -> None:
    """Validate previous GPA and completed credit hours.

    Args:
        current_gpa: GPA before the planned semester.
        completed_credits: Previously completed GPA credit hours.

    Raises:
        HTTPException: If these totals are invalid or contradict each other.
    """
    if not math.isfinite(current_gpa) or not 0 <= current_gpa <= MAX_GPA:
        raise HTTPException(400, "Current GPA must be between 0.0 and 4.3.")
    if completed_credits < 0:
        raise HTTPException(400, "Completed credits cannot be negative.")
    if completed_credits == 0 and current_gpa != 0:
        raise HTTPException(
            400, "Current GPA must be 0.0 when no credits have been completed."
        )


def total_credits(classes: list[GpaCourse]) -> int:
    """Add the positive credit hours for the supplied courses.

    Args:
        classes: Courses whose credit hours should be added.

    Returns:
        The sum of course credit hours.

    Raises:
        HTTPException: If a course has zero or negative credits.
    """
    credits: int = 0
    for course in classes:
        if course.credit <= 0:
            raise HTTPException(
                400, "Course credits must be greater than zero."
            )
        credits += course.credit
    return credits


def semester_gpa(classes: list[GpaCourse]) -> float:
    """Return a credit-weighted GPA for the supplied courses.

    Args:
        classes: Courses with credit hours and expected grade points.

    Returns:
        Total quality points divided by total credit hours.

    Raises:
        HTTPException: If no courses or unsupported grades are supplied.
    """
    if not classes:
        raise HTTPException(400, "Enter at least one course.")
    credit_hours: int = total_credits(classes)
    quality_points: float = 0.0
    for course in classes:
        if course.grade not in GRADE_POINTS.values():
            raise HTTPException(400, "Choose a valid LSU letter grade.")
        quality_points += course.grade * course.credit
    return min(MAX_GPA, quality_points / credit_hours)


def cumulative_gpa(data: CumulativeGPARequest) -> float:
    """Combine previous quality points with the planned semester.

    Args:
        data: Previous GPA, completed credits, and planned courses.

    Returns:
        The projected cumulative GPA without premature rounding.

    Raises:
        HTTPException: If previous totals or planned courses are invalid.
    """
    check_history(data.current_gpa, data.completed_credits)
    semester_average: float = semester_gpa(data.classes)
    semester_credits: int = total_credits(data.classes)
    previous_points: float = data.current_gpa * data.completed_credits
    semester_points: float = semester_average * semester_credits
    combined_credits: int = data.completed_credits + semester_credits
    return min(MAX_GPA, (previous_points + semester_points) / combined_credits)


def required_gpa(data: RequiredGPARequest) -> float:
    """Calculate the semester GPA needed to reach a cumulative target.

    Args:
        data: Current GPA, completed credits, planned credits, and target GPA.

    Returns:
        The required semester GPA, bounded below by zero.

    Raises:
        HTTPException: If inputs are invalid or the target is unreachable.
    """
    check_history(data.current_gpa, data.completed_credits)
    if (
        not math.isfinite(data.target_gpa)
        or not 0 <= data.target_gpa <= MAX_GPA
    ):
        raise HTTPException(400, "Target GPA must be between 0.0 and 4.3.")
    if data.planned_credits <= 0:
        raise HTTPException(400, "Planned credits must be greater than zero.")
    combined_credits: int = data.completed_credits + data.planned_credits
    previous_points: float = data.current_gpa * data.completed_credits
    needed_gpa: float = (
        data.target_gpa * combined_credits - previous_points
    ) / data.planned_credits
    if needed_gpa > MAX_GPA + 1e-9:
        highest_gpa: float = (
            previous_points + MAX_GPA * data.planned_credits
        ) / combined_credits
        raise HTTPException(
            400,
            f"Target GPA is unreachable this semester. "
            f"The highest possible cumulative GPA is {highest_gpa:.2f}.",
        )
    return min(MAX_GPA, max(0.0, needed_gpa))


def saved_classes() -> list[GpaCourse]:
    """Report that saved-course retrieval still requires its database connection.

    Returns:
        No records until saved-course retrieval is implemented.

    Raises:
        HTTPException: Always reports the unfinished API with status 501.
    """
    raise HTTPException(501, "Saved course retrieval is not available yet.")


# Preserve the team's existing imports while new functions use snake_case.
calculateGPA = semester_gpa
calculateTotalCredits = total_credits
calculateCumlativeGPA = cumulative_gpa
calculateRequiredGPA = required_gpa
getClasses = saved_classes


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
        check_history(current_gpa, completed_credits)
        courses: list[GpaCourse] = read_courses(form.rows)
        result: PlanningResult = PlanningResult(
            semester_gpa=semester_gpa(courses),
            cumulative_gpa=cumulative_gpa(
                CumulativeGPARequest(
                    current_gpa=current_gpa,
                    completed_credits=completed_credits,
                    classes=courses,
                )
            ),
            planned_credits=total_credits(courses),
            current_gpa=current_gpa,
        )
    except ValueError as error:
        return None, [str(error)]
    except HTTPException as error:
        return None, [str(error.detail)]
    if not form.target_gpa.strip():
        return result, []
    try:
        target_gpa: float = read_number(form.target_gpa, "target GPA")
        result.required_gpa = required_gpa(
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
