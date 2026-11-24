"""Turn grids read from LSU Workday pages into grades, courses and a schedule."""

import re
from collections import Counter
from datetime import date, datetime
from typing import Any

from grade_scale import GRADE_POINTS
from models.tiger_schedules import WEEKDAYS, Weekday
from models.tiger_workday import (
    WorkdayCourse,
    WorkdayData,
    WorkdayPages,
    WorkdaySection,
    WorkdayTable,
)

UNKNOWN_TERM: str = "Unknown term"
TRANSFER_TERM: str = "Transfer Credit"
DAY_NAMES: dict[str, Weekday] = {
    **{day.lower(): day for day in WEEKDAYS},
    **{day[:3].lower(): day for day in WEEKDAYS},
    "m": "Monday", "t": "Tuesday", "tu": "Tuesday", "tues": "Tuesday",
    "w": "Wednesday", "th": "Thursday", "r": "Thursday", "thur": "Thursday",
    "thurs": "Thursday", "f": "Friday", "sa": "Saturday", "su": "Sunday",
}
# Compact day lists such as "MWF" or "TTh"; "Th" is tried before "T".
COMPACT_DAYS: str = r"(?:th|tu|sa|su|m|t|w|r|f)"
CLOCK_PATTERN: re.Pattern[str] = re.compile(r"(\d{1,2}):(\d\d)\s*(?:([AP])M)?", re.I)
DATES_PATTERN: re.Pattern[str] = re.compile(
    r"\((\d\d/\d\d/\d{4})\s*-\s*(\d\d/\d\d/\d{4})\)"
)


def to_number(text: str | None) -> float | None:
    """Read a number from a grid cell.

    Args:
        text: Cell text.

    Returns:
        The number, or None when the cell is not numeric.
    """
    try:
        return float(text or "")
    except ValueError:
        return None


def whole_credits(text: str | None) -> int | None:
    """Read a credit-hours cell as whole credits, rounding halves up.

    Profile courses store whole credits, so this is the one place Workday
    credit hours are converted; courses, sections and GPA totals all use it.

    Args:
        text: Cell text, such as "3" or "2.5".

    Returns:
        The whole credits, such as 3 for "2.5", or None when not numeric.
    """
    value = to_number(text)
    return None if value is None else int(value + 0.5)


def split_listing(listing: str) -> tuple[str, str]:
    """Split a Workday course listing into its code and title.

    Args:
        listing: Text such as "CSC 1350 - Computer Science I".

    Returns:
        The upper-case course code and the title.
    """
    code, _, title = listing.partition(" - ")
    return code.strip().upper(), title.strip()


def term_dates(period: str) -> tuple[date, date]:
    """Read the first and last day of an academic period.

    Args:
        period: Text such as "2024 Fall Semester (08/24/2024-12/14/2024)".

    Returns:
        Start and end dates; both are the latest possible date when the
        period gives none, so undated terms sort last.
    """
    found = DATES_PATTERN.search(period)
    if not found:
        return date.max, date.max
    start, end = (datetime.strptime(day, "%m/%d/%Y").date() for day in found.groups())
    return start, end


def term_name(period: str) -> str:
    """Drop the date range from an academic period.

    Args:
        period: Text such as "2024 Fall Semester (08/24/2024-12/14/2024)".

    Returns:
        The bare name, such as "2024 Fall Semester".
    """
    return re.sub(r"\s*\([^()]*\)\s*$", "", period).strip()


def course_periods(progress: list[WorkdayTable]) -> dict[str, str]:
    """Map each course code to the academic period it was taken in.

    Args:
        progress: Grids from "My Academic Progress".

    Returns:
        Academic period by course code.
    """
    return {
        split_listing(row["Registrations Used"])[0]: row["Academic Period"]
        for table in progress
        for row in table.rows
        if row.get("Registrations Used") and row.get("Academic Period")
    }


def table_period(codes: list[str], periods: dict[str, str]) -> str:
    """Name the period of one record grid, which does not say its own term.

    Args:
        codes: Course codes in the grid.
        periods: Academic period by course code, from academic progress.

    Returns:
        The period most of the grid's courses were taken in.
    """
    votes = Counter(periods[code] for code in codes if code in periods)
    return votes.most_common(1)[0][0] if votes else UNKNOWN_TERM


def graded_courses(
    table: WorkdayTable, periods: dict[str, str]
) -> list[WorkdayCourse]:
    """Read the graded courses of one record grid; in-progress ones are skipped.

    Args:
        table: One grid from "My Academic Record".
        periods: Academic period by course code, from academic progress.

    Returns:
        The grid's courses, each with its term and grade.
    """
    rows = [row for row in table.rows if row.get("Course") and row.get("Grade", "").strip()]
    listings = [split_listing(row["Course"]) for row in rows]
    term = term_name(table_period([code for code, _ in listings], periods))
    return [
        WorkdayCourse(
            course_code=code,
            course_name=title,
            credits=whole_credits(row.get("Credit Hours")) or 0,
            term=term,
            grade=row["Grade"].strip(),
        )
        for (code, title), row in zip(listings, rows)
    ]


def transfer_courses(record: list[WorkdayTable]) -> list[WorkdayCourse]:
    """Collect transfer and exam credit, counting each course once.

    The same course is often granted by several exams.

    Args:
        record: Grids from "My Academic Record".

    Returns:
        One course per code, in the "Transfer Credit" term.
    """
    courses: dict[str, WorkdayCourse] = {}
    for row in (row for table in record for row in table.rows):
        code, title = split_listing(row.get("Transfer Credit", ""))
        if code and code not in courses:
            courses[code] = WorkdayCourse(
                course_code=code,
                course_name=title,
                credits=whole_credits(row.get("Credit Hours")) or 0,
                term=TRANSFER_TERM,
                grade=row.get("Grade", "").strip(),
            )
    return list(courses.values())


def past_courses(pages: WorkdayPages) -> list[WorkdayCourse]:
    """Collect every graded course, transfer credit first, then oldest term first.

    Args:
        pages: Grids from the three Workday pages.

    Returns:
        Past courses in term order, record order within a term.
    """
    periods = course_periods(pages.progress)
    starts = {term_name(period): term_dates(period)[0] for period in periods.values()}
    courses = [
        course for table in pages.record for course in graded_courses(table, periods)
    ]
    ordered = sorted(courses, key=lambda course: starts.get(course.term, date.max))
    return transfer_courses(pages.record) + ordered


def gpa_totals(record: list[WorkdayTable]) -> tuple[float | None, int]:
    """Total the institutional GPA hours and earned grade points.

    Args:
        record: Grids from "My Academic Record".

    Returns:
        The cumulative GPA, or None without GPA hours, and the GPA hours.
    """
    hours: int = 0
    points: float = 0
    for row in (row for table in record for row in table.rows):
        credits = whole_credits(row.get("Credit Hours"))
        earned = to_number(row.get("Earned Grade Points"))
        if row.get("Course") and credits and earned is not None:
            hours += credits
            points += earned
    return (round(points / hours, 3) if hours else None), hours


def term_gpas(courses: list[WorkdayCourse]) -> dict[str, float]:
    """Compute each term's GPA from saved courses with the LSU grade scale.

    Grades outside the scale (W, P, in-progress, transfer) do not count.

    Args:
        courses: Courses carrying their term, grade and credit hours.

    Returns:
        GPA by term name, rounded to 3 places, in first-seen term order.
    """
    points: dict[str, float] = {}
    hours: dict[str, int] = {}
    for course in courses:
        grade = course.grade.strip()
        if grade in GRADE_POINTS and course.credits:
            earned = GRADE_POINTS[grade] * course.credits
            points[course.term] = points.get(course.term, 0) + earned
            hours[course.term] = hours.get(course.term, 0) + course.credits
    return {term: round(points[term] / hours[term], 3) for term in hours}


def clock_time(hour: str, minute: str, half: str) -> str:
    """Write a 12-hour clock time as 24-hour HH:MM.

    Args:
        hour: Hour from 1 to 12.
        minute: Two-digit minute.
        half: "A" or "P", either case.

    Returns:
        The time as HH:MM.
    """
    return f"{int(hour) % 12 + (12 if half.upper() == 'P' else 0):02d}:{minute}"


def clock_times(text: str) -> tuple[str | None, str | None]:
    """Read a meeting time such as "9:00 AM - 10:20 AM" as 24-hour times.

    The start may share the end's AM/PM, as in "9:00-10:20 AM".

    Args:
        text: The time part of a meeting pattern.

    Returns:
        Start and end as HH:MM, or (None, None) without two times or when
        the end is not after the start.
    """
    found = CLOCK_PATTERN.findall(text)
    if len(found) < 2 or not found[1][2]:
        return None, None
    (start_hour, start_minute, start_half), (hour, minute, half) = found[:2]
    end = clock_time(hour, minute, half)
    start = clock_time(start_hour, start_minute, start_half or half)
    if not start_half and start > end:
        start = clock_time(start_hour, start_minute, "A")
    return (start, end) if start < end else (None, None)


def meeting_days(text: str) -> list[Weekday]:
    """Read meeting days written out, abbreviated or run together.

    Args:
        text: Days such as "Monday Wednesday", "Mon/Wed", "M, W" or "MWF".

    Returns:
        The weekdays in order given, each once; unknown words are ignored.
    """
    days: list[Weekday] = []
    for word in re.split(r"[\s,/]+", text.lower()):
        if word in DAY_NAMES:
            days.append(DAY_NAMES[word])
        elif re.fullmatch(f"{COMPACT_DAYS}+", word):
            days += [DAY_NAMES[part] for part in re.findall(COMPACT_DAYS, word)]
    return list(dict.fromkeys(days))


def read_section(row: dict[str, str]) -> WorkdaySection:
    """Read one registered section from a "View My Courses" row.

    Args:
        row: Grid row keyed by column header.

    Returns:
        The section, with its meeting pattern split into days, times and room.
    """
    code, title = split_listing(row.get("Course Listing", ""))
    parts = [part.strip() for part in row.get("Meeting Patterns", "").split("|")]
    days, time, room = (parts + ["", ""])[:3]
    start, end = clock_times(time)
    status = row.get("Registration Status", "")
    return WorkdaySection(
        course_code=code,
        course_name=title,
        credits=whole_credits(row.get("Credit Hours")) or 0,
        section=row.get("Section", ""),
        format=row.get("Instructional Format", ""),
        status=status,
        dropped=bool(re.search(r"drop|withdr", status, re.I)),
        days=meeting_days(days),
        start=start,
        end=end,
        location=room,
    )


def term_sections(
    courses: list[WorkdayTable], period: str
) -> list[WorkdaySection]:
    """Read every enrolled section listed under one term; waitlists are skipped.

    A row with a blank course listing is another meeting (a lab or
    recitation) of the course above it, as in the original scraper.

    Args:
        courses: Grids from "View My Courses".
        period: The term heading to read.

    Returns:
        The term's sections in page order.
    """
    sections: list[WorkdaySection] = []
    for table in courses:
        if (table.semester or UNKNOWN_TERM) != period or "Waitlist" in table.title:
            continue
        listing = ""
        for row in table.rows:
            listing = row.get("Course Listing") or listing
            if listing:
                sections.append(read_section({**row, "Course Listing": listing}))
    return sections


def current_period(courses: list[WorkdayTable], today: date) -> str:
    """Pick the registered term that is under way or comes next.

    Args:
        courses: Grids from "View My Courses", headed by their term.
        today: The date to compare term dates against.

    Returns:
        The first term not over by today, else the last term to end, else
        an empty string when nothing is registered.
    """
    headings = (table.semester or UNKNOWN_TERM for table in courses)
    periods = list(dict.fromkeys(headings))
    if not periods:
        return ""
    running = [period for period in periods if term_dates(period)[1] >= today]
    if running:
        return min(running, key=lambda period: term_dates(period)[0])
    return max(periods, key=lambda period: term_dates(period)[1])


def parse_workday(raw: dict[str, Any], today: date) -> WorkdayData:
    """Read one sync's worth of Workday page grids.

    Args:
        raw: {"courses": [...], "record": [...], "progress": [...]}, each a
            list of grids as workday-extract.js returns them.
        today: The date that decides which registered term is current.

    Returns:
        GPA, GPA hours, past courses, and the current term's sections.
    """
    pages = WorkdayPages.model_validate(raw)
    gpa, hours = gpa_totals(pages.record)
    period = current_period(pages.courses, today)
    return WorkdayData(
        gpa=gpa,
        completed_credit_hours=hours,
        courses=past_courses(pages),
        term=term_name(period),
        sections=term_sections(pages.courses, period),
    )
