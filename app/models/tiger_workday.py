"""Grades, courses, and the current class schedule read from LSU Workday."""

from pydantic import BaseModel, Field

from models.tiger_profiles import ProfileCourse
from models.tiger_schedules import Weekday


class WorkdayTable(BaseModel):
    """One grid as the page script returns it.

    Attributes:
        semester: The nearest section heading above the grid, if any.
        title: The grid's own title, such as "My Enrolled Courses".
        rows: One mapping of column header to visible cell text per row.
    """

    semester: str | None = None
    title: str = ""
    rows: list[dict[str, str]] = Field(default_factory=list)


class WorkdayPages(BaseModel):
    """The grids read from the three Workday pages the scraper visits.

    Attributes:
        courses: Grids from "View My Courses".
        record: Grids from "My Academic Record".
        progress: Grids from "My Academic Progress".
    """

    courses: list[WorkdayTable] = Field(default_factory=list)
    record: list[WorkdayTable] = Field(default_factory=list)
    progress: list[WorkdayTable] = Field(default_factory=list)


class WorkdaySection(BaseModel):
    """One registered section of a current-term course, such as a lab.

    Attributes:
        course_code: Course code, such as "CSC 3102".
        course_name: Course title.
        credits: Credit hours of the course.
        section: Section name as Workday shows it.
        format: Instructional format, such as "Lecture" or "Lab".
        status: Registration status as Workday shows it.
        dropped: True when the section was dropped or withdrawn.
        days: Meeting days; empty when the section has no set time.
        start: Start time as 24-hour HH:MM, or None when not set.
        end: End time as 24-hour HH:MM, or None when not set.
        location: Building and room, empty when not set.
    """

    course_code: str
    course_name: str
    credits: int = 0
    section: str = ""
    format: str = ""
    status: str = ""
    dropped: bool = False
    days: list[Weekday] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    location: str = ""


class WorkdayData(BaseModel):
    """Everything one Workday sync yields.

    Attributes:
        gpa: Cumulative institutional GPA, or None before any graded hours.
        completed_credit_hours: Institutional GPA hours, including F grades.
        courses: Past courses with term and grade set, oldest term first;
            in-progress ones left out.
        term: Current term name, empty when no term is registered.
        sections: The current term's sections, dropped ones flagged.
    """

    gpa: float | None = Field(default=None, ge=0, le=4.3)
    completed_credit_hours: int = Field(default=0, ge=0)
    courses: list[ProfileCourse] = Field(default_factory=list)
    term: str = ""
    sections: list[WorkdaySection] = Field(default_factory=list)


class WorkdayStatus(BaseModel):
    """Whether Workday sync can run here and when it last ran.

    Attributes:
        available: True only when the app runs locally with Playwright.
        connected: True once the student has synced at least once.
        last_sync: UTC time of the last sync, or None.
    """

    available: bool
    connected: bool
    last_sync: str | None = None


class WorkdaySync(BaseModel):
    """What one sync saved.

    Attributes:
        gpa: Cumulative GPA now saved on the profile.
        completed_credit_hours: GPA hours now saved on the profile.
        courses_added: Courses added to the profile.
        classes_added: Classes added to the term's schedule.
        schedule: Name of the term's schedule, empty without a current term.
        schedule_created: True when this sync created that schedule, also
            when the student had deleted it.
        last_sync: UTC time of this sync.
    """

    gpa: float | None
    completed_credit_hours: int
    courses_added: int
    classes_added: int
    schedule: str
    schedule_created: bool
    last_sync: str
