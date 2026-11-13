"""Validate the optional academic fields returned by the profile backend."""

from pydantic import BaseModel, ConfigDict, Field


class ProfileCourse(BaseModel):
    """A completed course supplied by the profile backend."""

    course_code: str
    course_name: str
    credits: int = Field(ge=0)


class ProfileRecord(BaseModel):
    """The profile table fields used by the read-only account page."""

    model_config = ConfigDict(allow_inf_nan=False)
    username: str | None = None
    gpa: float | None = Field(default=None, ge=0, le=4.3)
    courses: list[ProfileCourse] = Field(default_factory=list)
