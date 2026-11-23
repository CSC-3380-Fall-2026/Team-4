"""Validate account credentials and the academic fields of a profile."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserAuthSchema(BaseModel):
    """Email and password submitted for login or signup."""

    email: EmailStr
    password: str


class ProfileCourse(BaseModel):
    """A completed course supplied by the profile backend."""

    course_code: str
    course_name: str
    credits: int = Field(ge=0)


class ParsedTranscript(BaseModel):
    """GPA, credit hours, and completed courses, as read from a transcript."""

    gpa: float | None = Field(default=None, ge=0, le=4.3)
    completed_credit_hours: int = Field(default=0, ge=0)
    courses: list[ProfileCourse] = Field(default_factory=list)


class ProfileRecord(ParsedTranscript):
    """The editable profile fields, as stored or as submitted by a student."""

    model_config = ConfigDict(allow_inf_nan=False)
    username: str | None = None


ProfileUpdate = ProfileRecord
