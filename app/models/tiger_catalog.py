"""Catalog courses, concentration requirements, and prerequisite checks."""

from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ScrapedCourse(BaseModel):
    """A course scraped from the catalog."""

    id: str
    course_code: str
    course_name: str
    credits: int
    category: str
    source_url: str


class ConcentrationRequirements(BaseModel):
    """Courses and notes required for a concentration."""

    required_courses: list[ScrapedCourse] = Field(default_factory=list)
    approved_electives: list[ScrapedCourse] = Field(default_factory=list)
    other_requirements: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    required_credit_hours: int | None = None


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


class PrerequisiteRequest(BaseModel):
    """Request body for a prerequisite check."""

    course_code: str
    completed: dict[str, str] = Field(default_factory=dict)
    registered: set[str] = Field(default_factory=set)
