"""Prerequisite checking for supported courses.

Tests import this file as app.tiger_prerequisites, without app/ on the
import path, so it keeps its own models and imports nothing from app/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing_extensions import TypedDict


DATA_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "course_prerequisites.json"
)


class Requirement(TypedDict, total=False):
    """Prerequisite option group with optional grade and registration rules."""

    any_of: list[str]
    credit_or_registration: bool
    min_grade: str


class CourseResult(TypedDict):
    """Outcome of evaluating one course's prerequisites."""

    course_code: str
    satisfied: list[str]
    missing: list[str]
    cannot_evaluate: list[str]
    eligible: bool


GRADE_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F": 0.0,
}


def load_prerequisites() -> dict:
    """Read the prerequisite catalog from disk.

    Returns:
        Mapping of course code to its prerequisite data.
    """
    with DATA_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def grade_meets(grade: str, minimum: str | None) -> bool | None:
    """Compare a letter grade with a required minimum.

    Args:
        grade: The student's letter grade.
        minimum: Required letter grade, or None for any grade.

    Returns:
        True or False for a known grade, None when the grade is unknown.
    """
    if minimum is None:
        return True
    if grade not in GRADE_POINTS:
        return None
    return GRADE_POINTS[grade] >= GRADE_POINTS[minimum]


def check_requirement(
    requirement: Requirement,
    completed: dict[str, str],
    registered: set[str],
) -> tuple[bool, bool]:
    """Evaluate one any-of requirement.

    Args:
        requirement: The requirement with its options and rules.
        completed: Completed courses mapped to letter grades.
        registered: Courses currently registered for.

    Returns:
        A pair of (satisfied, unknown_grade).
    """
    minimum = requirement.get("min_grade")
    allows_registration = requirement.get("credit_or_registration", False)
    satisfied = False
    unknown = False
    for option in requirement["any_of"]:
        if option in completed:
            met = grade_meets(completed[option].upper(), minimum)
            satisfied = satisfied or bool(met)
            unknown = unknown or (met is None and minimum is not None)
        if allows_registration and option in registered:
            satisfied = True
    return satisfied, unknown


def check_prerequisites(
    course_code: str,
    completed: dict[str, str],
    registered: set[str] | None = None,
) -> CourseResult:
    """Check completed grades and current registration.

    Args:
        course_code: Course whose prerequisites are evaluated.
        completed: Completed courses mapped to letter grades.
        registered: Courses currently registered for.

    Returns:
        Which requirements are satisfied, missing, or unverifiable.

    Raises:
        ValueError: If the course is not in the catalog.
    """
    registered = registered or set()
    catalog = load_prerequisites()
    if course_code not in catalog:
        raise ValueError(f"Unsupported course: {course_code}")
    course = catalog[course_code]
    result: CourseResult = {
        "course_code": course_code,
        "satisfied": [],
        "missing": [],
        "cannot_evaluate": [],
        "eligible": False,
    }
    for requirement in course.get("requirements", []):
        met, unknown = check_requirement(requirement, completed, registered)
        text = " or ".join(requirement["any_of"])
        if met:
            result["satisfied"].append(text)
        elif unknown:
            result["cannot_evaluate"].append(
                f"Grade needs verification: {text}"
            )
        else:
            result["missing"].append(text)
    result["cannot_evaluate"].extend(course.get("unverified_requirements", []))
    result["eligible"] = (
        not result["missing"] and not result["cannot_evaluate"]
    )
    return result

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()


class PrerequisiteRequest(BaseModel):
    """Request body for a prerequisite check."""

    course_code: str
    completed: dict[str, str] = Field(default_factory=dict)
    registered: set[str] = Field(default_factory=set)


@router.post("/courses/check-prerequisites", tags=["Course Catalog"])
def check_course(request: PrerequisiteRequest) -> CourseResult:
    """Return prerequisite status for a requested course.

    Args:
        request: Course code with completed and registered courses.

    Returns:
        The prerequisite evaluation result.

    Raises:
        HTTPException: 404 if the course is unsupported.
    """
    try:
        return check_prerequisites(
            request.course_code,
            request.completed,
            request.registered,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
