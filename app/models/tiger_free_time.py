"""Shared free time request and response models with camelCase JSON aliases."""

from pydantic import Field, field_validator, model_validator

from models.tiger_schedules import ScheduleModel, Weekday, check_time, required_text


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
