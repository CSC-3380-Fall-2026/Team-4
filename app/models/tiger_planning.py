"""Separate raw form values from data needed for GPA calculations."""

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, field_validator

from grade_scale import GRADE_POINTS


class GpaCourse(BaseModel):
    """Course credits and grade points without invented meeting information."""

    model_config = ConfigDict(from_attributes=True)
    credit: int
    grade: float

    @field_validator("grade", mode="before")
    @classmethod
    def grade_value(cls, value: object) -> object:
        """Convert a letter grade while preserving numeric API inputs.

        Args:
            value: The submitted letter grade or numeric grade points.

        Returns:
            Grade points, or the original value for normal validation.
        """
        if isinstance(value, str) and value.strip().upper() in GRADE_POINTS:
            return GRADE_POINTS[value.strip().upper()]
        return value

    @field_validator("credit", mode="before")
    @classmethod
    def credit_value(cls, value: object) -> object:
        """Reject boolean credits before integer conversion.

        Args:
            value: Submitted course credit hours.

        Returns:
            The original value when it is not a boolean.

        Raises:
            ValueError: If true or false was supplied instead of credits.
        """
        if isinstance(value, bool):
            raise ValueError("Credits must be a whole number.")
        return value


class CumulativeGPARequest(BaseModel):
    """Previous academic totals and courses for a cumulative forecast."""

    model_config = ConfigDict(populate_by_name=True)
    current_gpa: float = Field(alias="currentGPA")
    completed_credits: int = Field(alias="completedCredits")
    classes: list[GpaCourse]


class RequiredGPARequest(BaseModel):
    """Previous totals and a target for the required semester calculation."""

    model_config = ConfigDict(populate_by_name=True)
    current_gpa: float = Field(alias="currentGPA")
    completed_credits: int = Field(alias="completedCredits")
    planned_credits: int = Field(alias="plannedCredits")
    target_gpa: float = Field(alias="targetGPA")


@dataclass
class CourseRow:
    """Keep each submitted row as text so invalid entries can be redisplayed."""

    name: str = ""
    credit: str = ""
    grade: str = ""


@dataclass
class PlanningForm:
    """Raw values entered in the Planning form."""

    current_gpa: str = ""
    completed_credits: str = ""
    target_gpa: str = ""
    rows: list[CourseRow] = field(default_factory=list)


class PlanningResult(BaseModel):
    """Computed forecast values suitable for the page and dashboard."""

    semester_gpa: float = Field(ge=0, le=4.3)
    cumulative_gpa: float = Field(ge=0, le=4.3)
    planned_credits: int = Field(gt=0)
    required_gpa: float | None = Field(default=None, ge=0, le=4.3)
    target_error: str = ""
