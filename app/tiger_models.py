"""Typed models shared by application routes and services."""

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

Weekday = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

ScheduleColor = Literal[
    "blue", "green", "orange", "purple", "red", "yellow", "pink", "teal"
]

def to_camel(value: str) -> str:
    """Convert a snake_case name to camelCase.

    Args:
        value: The snake_case field name.

    Returns:
        The camelCase alias.
    """
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ScheduleModel(BaseModel):
    """Base model that accepts and emits camelCase aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class UserAuthSchema(BaseModel):
    """Email and password submitted for login or signup."""

    email: EmailStr
    password: str

class ScheduleEventData(ScheduleModel):
    """Validated fields shared by every schedule event."""

    title: str = Field(min_length=1, max_length=100)
    days: list[Weekday] = Field(min_length=1)
    start: str
    end: str
    location: str = Field(default="", max_length=120)
    guests: list[str] = Field(default_factory=list)
    favorite: bool = False

    @field_validator("title", "location")
    @classmethod
    def strip_text(cls: type["ScheduleEventData"], value: str) -> str:
        """Strip surrounding whitespace from text fields.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return value.strip()

    @field_validator("title")
    @classmethod
    def require_title(cls: type["ScheduleEventData"], value: str) -> str:
        """Reject an event title that is blank.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        if not value:
            raise ValueError("Event title cannot be blank.")
        return value

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls: type["ScheduleEventData"], value: str) -> str:
        """Require 24-hour HH:MM time format.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Event times must use 24-hour HH:MM format.")
        return value

    @field_validator("days", mode="before")
    @classmethod
    def normalize_days(cls: type["ScheduleEventData"], days: list[str]) -> list[str]:
        """Expand day abbreviations to full weekday names.

        Args:
            days: The submitted value.

        Returns:
            The cleaned value.
        """
        day_names = {
            "M": "Monday",
            "T": "Tuesday",
            "W": "Wednesday",
            "Th": "Thursday",
            "F": "Friday",
            "Sa": "Saturday",
            "Su": "Sunday",
        }
        return [day_names.get(day, day) for day in days]

    @model_validator(mode="after")
    def require_duration(self) -> "ScheduleEventData":
        """Ensure the event ends after it starts.

        Returns:
            This model when valid.
        """
        if self.end <= self.start:
            raise ValueError("End time must be after start time.")
        return self

    @field_validator("guests", mode="before")
    @classmethod
    def normalize_guests(cls: type["ScheduleEventData"], guests: list[str] | str) -> list[str]:
        """Split and clean the guest list.

        Args:
            guests: The submitted value.

        Returns:
            The cleaned value.
        """
        if isinstance(guests, str):
            guests = guests.split(",")
        return [guest.strip() for guest in guests if guest.strip()]

class ScheduleEvent(ScheduleEventData):
    """A schedule event with a unique ID."""

    id: str = Field(default_factory=lambda: str(uuid4()))

class Classes(ScheduleEvent):
    """A scheduled class event with course and grade details."""

    department: str
    number: int
    grade: float
    semester: str
    category: str
    credit: int = Field(gt=0)  ##credit hours are stored explicitly, never derived from meeting times

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

class CoursePreset(Classes):
    """A class preset with section and professor details."""

    course_id: str
    professor: str
    enrollment: str
    section_details: str

class Schedule(ScheduleModel):
    """A named, colored schedule holding events."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor
    events: list[Classes | ScheduleEvent] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls: type["Schedule"], value: str) -> str:
        """Strip and require a non-blank schedule name.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        value = value.strip()
        if not value:
            raise ValueError("Schedule title cannot be blank.")
        return value

class ScheduleDefinition(ScheduleModel):
    """The name and color used to create a schedule."""

    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor

    @field_validator("name")
    @classmethod
    def strip_name(cls: type["ScheduleDefinition"], value: str) -> str:
        """Strip and require a non-blank schedule name.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        value = value.strip()
        if not value:
            raise ValueError("Schedule title cannot be blank.")
        return value

class CourseSelection(ScheduleModel):
    """The ID of a course chosen to add."""

    course_id: str

class UserBase(ScheduleModel):
    """A user profile with GPA, courses, and schedules."""

    id: str | int
    username: str | None = None
    email: str
    gpa: float | None = None
    completed_credit_hours: int = 0
    courses: list[Any] = Field(default_factory=list)
    schedules: list[Schedule] = Field(default_factory=list)

class ScheduleMetrics(ScheduleModel):
    """Summary totals for one schedule."""

    total_hours: int
    days_busy: str

class SharedFreeTimeRequest(ScheduleModel):
    """Search window and friend for shared free time."""

    friend_username: str = Field(min_length=1)
    start_time: str
    end_time: str
    minimum_duration: int = Field(gt=0, le=1440)

    @field_validator("friend_username")
    @classmethod
    def strip_friend(cls: type["SharedFreeTimeRequest"], value: str) -> str:
        """Strip and require a non-blank friend username.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        value = value.strip()
        if not value:
            raise ValueError("Friend username cannot be blank.")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls: type["SharedFreeTimeRequest"], value: str) -> str:
        """Require 24-hour HH:MM time format.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Times must use 24-hour HH:MM format.")
        return value

    @model_validator(mode="after")
    def require_range(self) -> "SharedFreeTimeRequest":
        """Ensure the time range ends after it starts.

        Returns:
            This model when valid.
        """
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time.")
        return self


class SharedFreeTimePeriod(ScheduleModel):
    """A free time range within one day."""

    start: str
    end: str

class SharedFreeTimeDay(ScheduleModel):
    """Free time periods for one weekday."""

    day: Weekday
    periods: list[SharedFreeTimePeriod]

class SharedFreeTimeResponse(ScheduleModel):
    """Shared free time grouped by weekday."""

    days: list[SharedFreeTimeDay]

class ProfileUpdate(BaseModel):
    """Editable profile fields submitted by a student."""

    username: str | None = None
    gpa: float | None = Field(default=None, ge=0, le=4.3)
    completed_credit_hours: int = Field(default=0, ge=0)
    courses: list[Any] = Field(default_factory=list)
    
class Meeting(BaseModel):
    """A weekly meeting time for a section."""

    days: list[str]
    start: str
    end: str
    location: str = ""
    
class ScheduleSection(BaseModel):
    """A course section with its meetings."""

    department: str
    number: int
    name: str
    section: str
    credit: int = Field(default=3, gt=0)
    meetings: list[Meeting] = Field(default_factory=list)
    
class Commitment(BaseModel):
    """A non-course commitment on a schedule."""

    name: str
    days: list[str]
    start: str
    end: str
    notes: str = ""
    
class ScheduleIn(BaseModel):
    """Schedule data submitted when saving."""

    name: str = Field(min_length=1)
    semester: str
    sections: list[ScheduleSection] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    
class ScheduleOut(ScheduleIn):
    """A saved schedule with its ID and timestamps."""

    id: str
    created_at: str | None = None
    updated_at: str | None = None
    
class SchedulePageData(ScheduleModel):
    """Data needed to render the schedule page."""

    current_user_id: str | int
    users: list[UserBase]
    metrics: dict[str, ScheduleMetrics]

