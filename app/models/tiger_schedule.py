"""Schedule, event, and shared free time models with camelCase JSON aliases."""

import re
from typing import Any, Literal, get_args
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from models.tiger_friends import Friend

Weekday = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
WEEKDAYS: tuple[Weekday, ...] = get_args(Weekday)

ScheduleColor = Literal[
    "blue", "green", "orange", "purple", "red", "yellow", "pink", "teal"
]
TIME_PATTERN: str = r"(?:[01]\d|2[0-3]):[0-5]\d"


def to_camel(value: str) -> str:
    """Convert a snake_case name to camelCase.

    Args:
        value: The snake_case field name.

    Returns:
        The camelCase alias.
    """
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


def check_time(value: str, message: str) -> str:
    """Require 24-hour HH:MM time format.

    Args:
        value: The submitted time.
        message: Error shown when the format is wrong.

    Returns:
        The unchanged time.

    Raises:
        ValueError: If the time is not HH:MM.
    """
    if not re.fullmatch(TIME_PATTERN, value):
        raise ValueError(message)
    return value


def required_text(value: str, message: str) -> str:
    """Strip text and refuse it when nothing is left.

    Args:
        value: The submitted text.
        message: Error shown when the text is blank.

    Returns:
        The stripped text.

    Raises:
        ValueError: If the text is blank.
    """
    value = value.strip()
    if not value:
        raise ValueError(message)
    return value


class ScheduleModel(BaseModel):
    """Base model that accepts and emits camelCase aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ScheduleEventData(ScheduleModel):
    """Validated fields shared by every schedule event."""

    title: str = Field(min_length=1, max_length=100)
    days: list[Weekday] = Field(min_length=1)
    start: str
    end: str
    location: str = Field(default="", max_length=120)
    guests: list[str] = Field(default_factory=list)
    favorite: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls: type["ScheduleEventData"], value: str) -> str:
        """Strip and require a non-blank event title.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return required_text(value, "Event title cannot be blank.")

    @field_validator("location")
    @classmethod
    def strip_location(cls: type["ScheduleEventData"], value: str) -> str:
        """Strip surrounding whitespace from the location.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return value.strip()

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls: type["ScheduleEventData"], value: str) -> str:
        """Require 24-hour HH:MM time format.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return check_time(value, "Event times must use 24-hour HH:MM format.")

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

        Raises:
            ValueError: If the end time is not after the start time.
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
    credit: int = Field(gt=0)  # stored explicitly, never derived from meeting times


class CoursePreset(ScheduleModel):
    """A real catalog course offered for adding to a schedule."""

    course_id: str
    title: str
    course_name: str
    department: str
    number: int
    credit: int = Field(gt=0)
    category: str
    semester: str


class CourseSelection(ScheduleEventData):
    """A catalog course plus the meeting times the student chose for it."""

    course_id: str


class Schedule(ScheduleModel):
    """A named, colored schedule holding events."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=60)
    color: ScheduleColor
    events: list[Classes | ScheduleEvent] = Field(default_factory=list)
    # Stored entries this version can't read, written back unchanged on save.
    _kept: dict[str, list[Any]] = PrivateAttr(default_factory=dict)
    # The row's updated_at when loaded, used to refuse overwriting newer edits.
    _version: str | None = PrivateAttr(default=None)

    @field_validator("name")
    @classmethod
    def strip_name(cls: type["Schedule"], value: str) -> str:
        """Strip and require a non-blank schedule name.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return required_text(value, "Schedule title cannot be blank.")


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
        return required_text(value, "Schedule title cannot be blank.")


class UserBase(ScheduleModel):
    """A user profile with GPA, courses, and schedules."""

    id: str | int
    username: str | None = None
    email: str
    gpa: float | None = None
    completed_credit_hours: int = 0
    courses: list[Any] = Field(default_factory=list)
    schedules: list[Schedule] = Field(default_factory=list)
    # Filled by tiger_friends.load_friends; kept out of profile and schedule JSON.
    friends: list[Friend] = Field(default_factory=list, exclude=True)
    incoming_requests: list[Friend] = Field(default_factory=list, exclude=True)
    outgoing_requests: list[Friend] = Field(default_factory=list, exclude=True)


class ScheduleMetrics(ScheduleModel):
    """Summary totals for one schedule."""

    total_hours: int
    days_busy: str


class SchedulePageData(ScheduleModel):
    """Data needed to render the schedule page."""

    current_user_id: str | int
    users: list[UserBase]
    metrics: dict[str, ScheduleMetrics]


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
        return required_text(value, "Friend username cannot be blank.")

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls: type["SharedFreeTimeRequest"], value: str) -> str:
        """Require 24-hour HH:MM time format.

        Args:
            value: The submitted value.

        Returns:
            The cleaned value.
        """
        return check_time(value, "Times must use 24-hour HH:MM format.")

    @model_validator(mode="after")
    def require_range(self) -> "SharedFreeTimeRequest":
        """Ensure the time range ends after it starts.

        Returns:
            This model when valid.

        Raises:
            ValueError: If the end time is not after the start time.
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
