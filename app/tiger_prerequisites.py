
from __future__ import annotations

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
    any_of: list[str]
    credit_or_registration: bool
    min_grade: str


class CourseResult(TypedDict):
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
    with DATA_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def check_prerequisites(
    course_code: str,
    completed: dict[str, str],
    registered: set[str] | None = None,
) -> CourseResult:
    """Check completed grades and current registration."""
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
        options = requirement["any_of"]
        min_grade = requirement.get("min_grade")
        allows_registration = requirement.get(
            "credit_or_registration", False
        )

        satisfied = False
        unknown_grade = False

        for option in options:
            if option in completed:
                grade = completed[option].upper()

                if min_grade is None:
                    satisfied = True
                elif grade in GRADE_POINTS:
                    if GRADE_POINTS[grade] >= GRADE_POINTS[min_grade]:
                        satisfied = True
                else:
                    unknown_grade = True

            if allows_registration and option in registered:
                satisfied = True

        description = " or ".join(options)

        if satisfied:
            result["satisfied"].append(description)
        elif unknown_grade:
            result["cannot_evaluate"].append(
                f"Grade needs verification: {description}"
            )
        else:
            result["missing"].append(description)

    result["cannot_evaluate"].extend(
        course.get("unverified_requirements", [])
    )

    result["eligible"] = (
        not result["missing"]
        and not result["cannot_evaluate"]
    )

    return result

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()


class PrerequisiteRequest(BaseModel):
    course_code: str
    completed: dict[str, str] = Field(default_factory=dict)
    registered: set[str] = Field(default_factory=set)


@router.post("/courses/check-prerequisites", tags=["Course Catalog"])
def check_course_prerequisites(request: PrerequisiteRequest) -> CourseResult:
    try:
        return check_prerequisites(
            request.course_code,
            request.completed,
            request.registered,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
