"""Typed models shared by application routes and services."""

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
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

def to_camel_case(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ScheduleModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel_case,
        populate_by_name=True,
    )

class UserAuthSchema(BaseModel):
    email: EmailStr
    password: str

class ScheduleEventData(ScheduleModel):
    title: str = Field(min_length=1, max_length=100)
    days: list[Weekday] = Field(min_length=1)
    start: str
    end: str
    location: str = Field(default="", max_length=120)
    guests: list[str] = Field(default_factory=list)
    favorite: bool = False

    @field_validator("title", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("Event title cannot be blank.")
        return value

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Event times must use 24-hour HH:MM format.")
        return value

    @field_validator("days", mode="before")
    @classmethod
    def normalize_days(cls, days: list[str]) -> list[str]:
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
    def require_positive_duration(self) -> "ScheduleEventData":
        if self.end <= self.start:
            raise ValueError("End time must be after start time.")
        return self

    @field_validator("guests", mode="before")
    @classmethod
    def normalize_guests(cls, guests: list[str] | str) -> list[str]:
        if isinstance(guests, str):
            guests = guests.split(",")
        return [guest.strip() for guest in guests if guest.strip()]

class ScheduleEvent(ScheduleEventData):
    id: str = Field(default_factory=lambda: str(uuid4()))

class Classes(ScheduleEvent):
    department: str
    number: int
    grade: float
    semester: str
    category: str

    @computed_field
    @property
    def credit(self) -> int:
        # Preserves the existing calculation; this is based on meeting duration.
        start_hour, start_minute = map(int, self.start.split(":"))
        end_hour, end_minute = map(int, self.end.split(":"))
        duration_minutes = (
            (end_hour * 60 + end_minute)
            - (start_hour * 60 + start_minute)
        )
        return (duration_minutes + 59) // 60

class ScrapedCourse(BaseModel):
    id: str
    course_code: str
    course_name: str
    credits: int
    category: str
    source_url: str

class ConcentrationRequirements(BaseModel):
    required_courses: list[ScrapedCourse] = Field(default_factory=list)
    approved_electives: list[ScrapedCourse] = Field(default_factory=list)
    other_requirements: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    required_credit_hours: int | None = None

class CoursePreset(Classes):
    course_id: str
    professor: str
    enrollment: str
    section_details: str

class Schedule(ScheduleModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor
    events: list[Classes | ScheduleEvent] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Schedule title cannot be blank.")
        return value

class ScheduleDefinition(ScheduleModel):
    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Schedule title cannot be blank.")
        return value

class CourseSelection(ScheduleModel):
    course_id: str

class UserBase(ScheduleModel):
    id: str | int
    username: str | None = None
    email: str
    gpa: float | None = None
    courses: list[Any] = Field(default_factory=list)
    schedules: list[Schedule] = Field(default_factory=list)

class ScheduleMetrics(ScheduleModel):
    total_hours: int
    days_busy: str

class SharedFreeTimeRequest(ScheduleModel):
    friend_username: str = Field(min_length=1)
    start_time: str
    end_time: str
    minimum_duration: int = Field(gt=0, le=1440)

    @field_validator("friend_username")
    @classmethod
    def strip_friend_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Friend username cannot be blank.")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Times must use 24-hour HH:MM format.")
        return value

    @model_validator(mode="after")
    def require_positive_range(self) -> "SharedFreeTimeRequest":
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time.")
        return self


class SharedFreeTimePeriod(ScheduleModel):
    start: str
    end: str

class SharedFreeTimeDay(ScheduleModel):
    day: Weekday
    periods: list[SharedFreeTimePeriod]

class SharedFreeTimeResponse(ScheduleModel):
    days: list[SharedFreeTimeDay]

class ProfileUpdate(BaseModel):
    username: str | None = None
    gpa: float | None = Field(default=None, ge=0, le=4.3)
    courses: list[Any] = Field(default_factory=list)
    
class Meeting(BaseModel):
    days: list[str]
    start: str
    end: str
    location: str = ""
    
class ScheduleSection(BaseModel):
    department: str
    number: int
    name: str
    section: str
    credit: int = 0
    meetings: list[Meeting] = Field(default_factory=list)
    
class Commitment(BaseModel):
    name: str
    days: list[str]
    start: str
    end: str
    notes: str = ""
    
class ScheduleIn(BaseModel):
    name: str = Field(min_length=1)
    semester: str
    sections: list[ScheduleSection] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    
class ScheduleOut(ScheduleIn):
    id: str
    created_at: str | None = None
    updated_at: str | None = None
    
class SchedulePageData(ScheduleModel):
    current_user_id: str | int
    users: list[UserBase]
    metrics: dict[str, ScheduleMetrics]
