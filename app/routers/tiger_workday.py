"""Sync grades, courses and this term's classes from LSU Workday (local runs only).

What a sync saves, with no schema change:
- profile gpa and completed_credit_hours: replaced by Workday's every sync,
  except that a student with no grades yet keeps what is saved.
- profile courses: Workday courses the student lacks are added; a course is
  the same when its code and term match, and a saved course without a term
  matches any term. Saved courses are never changed, except by a reset,
  which replaces them all (unless Workday lists none).
- a schedule for this term and each later registered one, first named
  "<Term> (Workday)": sections not yet imported are added. Its commitments JSON keeps {"workday_term": term,
  "workday_imported": [section keys]}; that marker finds the schedule even
  after a rename, and an edited or deleted class is left alone. A deleted
  schedule is created again with every class.
- the last sync time: in the student's own account metadata.
"""

import logging
import os
import threading
from datetime import date, datetime, timezone
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from models.tiger_profiles import ProfileCourse, ProfileRecord
from models.tiger_schedules import (
    Classes,
    Schedule,
    ScheduleDefinition,
    ScheduleEvent,
)
from models.tiger_session import Session
from models.tiger_workday import (
    WorkdayData,
    WorkdaySection,
    WorkdayStatus,
    WorkdaySync,
    WorkdayTerm,
)
from routers import (
    tiger_profiles,
    tiger_schedules,
    tiger_schedules_store,
    tiger_workday_browser,
    tiger_workday_parsing,
)
from tiger_auth import current_session

NOT_LOCAL: str = "Workday sync is only available when running the app locally."
BUSY: str = "A Workday sync is already running. Finish it first."
NOTHING_CHANGED: str = "Workday pages could not be read; nothing was changed."
IMPORTED: str = "workday_imported"
TERM_KEY: str = "workday_term"
SUFFIX: str = " (Workday)"
RECORD_COLUMNS: set[str] = {"Course", "Grade", "Credit Hours"}
SYNC_LOCK: threading.Lock = threading.Lock()
LOG: logging.Logger = logging.getLogger(__name__)


def same_course(saved: ProfileCourse, found: ProfileCourse) -> bool:
    """Tell whether a saved course is the Workday course.

    Args:
        saved: A course already on the profile.
        found: A course read from Workday.

    Returns:
        True when the codes match and the saved term is blank or the same.
    """
    return saved.course_code == found.course_code and (
        not saved.term or saved.term == found.term
    )


def merge_courses(
    saved: list[ProfileCourse], found: list[ProfileCourse]
) -> list[ProfileCourse]:
    """Add the Workday courses the student does not have yet.

    Args:
        saved: Courses on the profile, kept as they are.
        found: Courses read from Workday.

    Returns:
        The saved courses followed by the missing Workday ones.
    """
    missing = [
        course for course in found if not any(same_course(old, course) for old in saved)
    ]
    return saved + missing


def section_event(
    schedule: Schedule, section: WorkdaySection, term: str, credits: int
) -> Classes | ScheduleEvent | None:
    """Turn a registered section into a schedule entry.

    A course's first meeting becomes the class carrying its credits; its
    other meetings (lab, recitation) are plain events so credits count once.

    Args:
        schedule: The term's schedule, to see if the course is on it.
        section: The Workday section.
        term: Current term name.
        credits: The course's credit hours.

    Returns:
        The entry, or None when the section has no set meeting time.
    """
    if not section.days or section.start is None or section.end is None:
        return None
    meeting = {
        "days": section.days,
        "start": section.start,
        "end": section.end,
        "location": section.location[:120],
    }
    department, _, number = section.course_code.partition(" ")
    listed = any(
        isinstance(event, Classes)
        and f"{event.department} {event.number}" == section.course_code
        for event in schedule.events
    )
    if listed or not number.isdigit() or credits <= 0:
        title = f"{section.course_code} {section.format}".strip()
        return ScheduleEvent(title=title[:100], **meeting)
    return Classes(
        title=section.course_code,
        department=department,
        number=int(number),
        grade=tiger_schedules.DEFAULT_GRADE,
        semester=term,
        category="Workday",
        credit=credits,
        **meeting,
    )


def workday_marker(schedule: Schedule) -> dict[str, Any] | None:
    """Find the Workday memory stored in a schedule's JSON.

    Args:
        schedule: Any of the student's schedules.

    Returns:
        {"workday_term": ..., "workday_imported": [...]}, or None when the
        schedule was not made by a Workday sync.
    """
    kept = schedule._kept.get("commitments", [])
    return next((item for item in kept if isinstance(item, dict) and IMPORTED in item), None)


def term_schedule(session: Session, term: str) -> tuple[Schedule, dict[str, Any], bool]:
    """Find the term's Workday schedule by its stored marker, or create it.

    The marker, not the name, identifies it, so a renamed schedule keeps
    its memory; a deleted one is created again.

    Args:
        session: The verified student.
        term: Current term name.

    Returns:
        The schedule, its marker, and True when it was just created.
    """
    schedules = tiger_schedules_store.list_schedules(session)
    for schedule in schedules:
        marker = workday_marker(schedule)
        if marker and marker.get(TERM_KEY) == term:
            return schedule, marker, False
    # Schedule names are unique per student, so step past one already taken.
    taken = {schedule.name.lower() for schedule in schedules}
    suffix, count = SUFFIX, 1
    while (name := term[: 60 - len(suffix)] + suffix).lower() in taken:
        count += 1
        suffix = f" (Workday {count})"
    schedule = tiger_schedules_store.insert_schedule(
        session, ScheduleDefinition(name=name, color="purple")
    )
    marker = {TERM_KEY: term, IMPORTED: []}
    schedule._kept.setdefault("commitments", []).append(marker)
    return schedule, marker, True


def import_schedule(session: Session, term: WorkdayTerm) -> tuple[str, int, bool]:
    """Add one term's new, not dropped sections to its schedule.

    Args:
        session: The verified student.
        term: A registered term and its sections.

    Returns:
        The schedule name, classes added, and whether the schedule was
        created by this sync.
    """
    schedule, marker, created = term_schedule(session, term.name)
    done: list[str] = marker[IMPORTED]
    added = 0
    for section in term.sections:
        key = f"{section.course_code} {section.section or section.format}"
        # Earlier syncs stored the section alone, or "code format".
        old = section.section or f"{section.course_code} {section.format}"
        if section.dropped or key in done or old in done:
            continue
        credits = max(
            part.credits for part in term.sections if part.course_code == section.course_code
        )
        event = section_event(schedule, section, term.name, credits)
        if event is None:
            continue
        schedule.events.append(event)
        done.append(key)
        added += 1
    if added or created:
        tiger_schedules_store.save_schedule(session, schedule)
    return schedule.name, added, created


def mark_synced(session: Session) -> str:
    """Record the sync time in the student's own account metadata.

    Args:
        session: The verified student.

    Returns:
        The sync time as an ISO UTC string.
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        requests.put(
            os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/user",
            headers={
                "apikey": os.environ["SUPABASE_KEY"],
                "Authorization": f"Bearer {session.token}",
            },
            json={"data": {tiger_workday_browser.SYNCED_KEY: stamp}},
            timeout=10,
        ).raise_for_status()
    except requests.RequestException:
        # The data is already saved; only the "last synced" time is lost.
        LOG.warning("Could not record the Workday sync time.", exc_info=True)
    return stamp


def save_sync(session: Session, data: WorkdayData, reset: bool) -> WorkdaySync:
    """Save one sync's data by the sync rules above.

    Args:
        session: The verified student.
        data: The parsed Workday pages.
        reset: True to replace every saved course with Workday's.

    Returns:
        What was saved.
    """
    row = tiger_profiles.profile_row(session)
    saved = tiger_profiles.readable_courses(row.get("courses"))
    found: list[ProfileCourse] = list(data.courses)
    # Nothing graded yet (a first term) never blanks what is saved.
    replace = reset and bool(found)
    courses = found if replace else merge_courses(saved, found)
    stored = tiger_profiles.write_profile(
        session,
        ProfileRecord(
            username=row.get("username"),
            gpa=data.gpa if data.gpa is not None else row.get("gpa"),
            completed_credit_hours=(
                data.completed_credit_hours or row.get("completed_credit_hours") or 0
            ),
            courses=courses,
        ),
    )
    imports = [import_schedule(session, term) for term in data.terms]
    return WorkdaySync(
        gpa=stored.gpa,
        completed_credit_hours=stored.completed_credit_hours,
        courses_added=len(courses) - (0 if replace else len(saved)),
        classes_added=sum(added for _, added, _ in imports),
        schedule=", ".join(name for name, _, _ in imports),
        schedule_created=any(created for _, _, created in imports),
        last_sync=mark_synced(session),
    )


def check_scrape(raw: dict[str, Any]) -> None:
    """Refuse a scrape whose pages could not be read, rather than empty ones.

    A first-term student has no graded courses yet, which is fine. A
    changed Workday page reads as a missing grid or column instead, and
    must not be saved over the student's GPA, hours, courses or classes.

    Args:
        raw: The grids as read from the pages, already parsed once.

    Raises:
        ValueError: When the record page has no course grid with Course,
            Grade and Credit Hours columns, or the courses page has rows
            but no "Course Listing" column.
    """
    record = [
        row
        for table in raw.get("record") or []
        for row in table.get("rows") or []
        if "Transfer Credit" not in row
    ]
    if not record or not all(RECORD_COLUMNS <= row.keys() for row in record):
        raise ValueError("The academic record was not read.")
    rows = [row for table in raw.get("courses") or [] for row in table.get("rows") or []]
    if rows and not any("Course Listing" in row for row in rows):
        raise ValueError("No classes were read.")


def run_sync(session: Session, reset: bool) -> WorkdaySync:
    """Read Workday in a browser window and save what it shows.

    Args:
        session: The verified student.
        reset: True to replace every saved course with Workday's.

    Returns:
        What was saved.

    Raises:
        HTTPException: 404 when not running locally, 409 while another sync
            runs, 502 when Workday could not be read.
    """
    if not tiger_workday_browser.workday_ready():
        raise HTTPException(404, NOT_LOCAL)
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(409, BUSY)
    try:
        raw = tiger_workday_browser.read_workday(session.user_id)
        data = tiger_workday_parsing.parse_workday(raw, date.today())
        check_scrape(raw)
        return save_sync(session, data, reset)
    except tiger_workday_browser.WorkdayError as error:
        raise HTTPException(502, str(error)) from error
    except ValueError as error:
        raise HTTPException(502, NOTHING_CHANGED) from error
    finally:
        SYNC_LOCK.release()


router: APIRouter = APIRouter(prefix="/api/workday")


@router.get("/status")
def workday_status(session: Session = Depends(current_session)) -> WorkdayStatus:
    """Say whether Workday sync is available here and when it last ran.

    Args:
        session: The verified student.

    Returns:
        Availability, whether the student has synced, and when.
    """
    return tiger_workday_browser.sync_status(session)


@router.post("/sync")
async def sync_workday(session: Session = Depends(current_session)) -> WorkdaySync:
    """Connect to Workday, or sync again, adding what is new.

    Args:
        session: The verified student.

    Returns:
        What was saved.
    """
    return await run_in_threadpool(run_sync, session, False)


@router.post("/reset")
async def reset_workday(session: Session = Depends(current_session)) -> WorkdaySync:
    """Sync from Workday, replacing every saved course with Workday's.

    Args:
        session: The verified student.

    Returns:
        What was saved.
    """
    return await run_in_threadpool(run_sync, session, True)
