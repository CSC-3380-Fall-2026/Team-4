"""Catalog courses and concentration requirements scraped from LSU pages."""

from typing import Any

from pydantic import BaseModel, Field


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

