"""Typed models shared by application routes and services."""
import re
from typing import Literal
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
ScheduleColor = Literal["blue", "green", "orange", "purple", "red", "yellow", "pink", "teal"]


def to_camel_case(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ScheduleModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel_case, populate_by_name=True)


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
        start_hour, start_minute = map(int, self.start.split(":"))
        end_hour, end_minute = map(int, self.end.split(":"))
        duration_minutes = (end_hour * 60 + end_minute) - (start_hour * 60 + start_minute)
        return (duration_minutes + 59) // 60


class Activites(ScheduleEvent):
    notes: str = ""


class CoursePreset(Classes):
    course_id: str
    professor: str
    enrollment: str
    section_details: str


class Schedule(ScheduleModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor
    events: list[Classes | Activites] = Field(default_factory=list)

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
    id: int
    username: str
    email: str
    gpa: int
    courses: list
    schedules: list[Schedule] = Field(default_factory=list)


class ScheduleMetrics(ScheduleModel):
    total_hours: int
    days_busy: str


class SchedulePageData(ScheduleModel):
    current_user_id: int
    users: list[UserBase]
    metrics: dict[str, ScheduleMetrics]