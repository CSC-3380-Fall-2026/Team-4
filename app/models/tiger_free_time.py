"""Shared free time request and response models with camelCase JSON aliases."""

from uuid import UUID

from pydantic import Field, field_validator, model_validator

from models.tiger_schedules import ScheduleModel, Weekday, check_time


class SharedFreeTimeRequest(ScheduleModel):
    """The friend and the student's schedule to compare, and the search window.

    Attributes:
        friend_id: The friend's user id, never their display label.
        schedule_id: The student's schedule to compare; None means their
            first schedule.
        start_time: Start of the search window as HH:MM.
        end_time: End of the search window as HH:MM.
        minimum_duration: Shortest free period in minutes.
    """

    friend_id: str = Field(min_length=1, max_length=100)
    schedule_id: UUID | None = None
    start_time: str
    end_time: str
    minimum_duration: int = Field(gt=0, le=1440)

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
