"""Calculate GPA with the existing formulas and compatible API addresses."""

import math

from fastapi import APIRouter, HTTPException

from grade_scale import GRADE_POINTS
from models.tiger_planning import (
    CumulativeGPARequest,
    GpaCourse,
    RequiredGPARequest,
)

router: APIRouter = APIRouter()
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


@router.post("/calculateTotalCredits")
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


@router.post("/calculateGPA")
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


@router.post("/calculateCumulativeGPA")
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


@router.post("/calculateRequiredGPA")
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


@router.post("/getClasses")
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
