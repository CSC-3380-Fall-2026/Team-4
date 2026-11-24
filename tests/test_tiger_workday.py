"""Check that a Workday sync never saves over data it could not read."""

import copy
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tiger_auth
from fake_supabase import FakeDatabase
from routers import tiger_schedules_store, tiger_workday, tiger_workday_browser
from tiger_app import app

JORDAN: dict[str, str] = {"Authorization": "Bearer token-jordan"}

SAVED: dict = {
    "id": "jordan",
    "username": "Jordan Example",
    "gpa": 3.5,
    "completed_credit_hours": 30,
    "courses": [{
        "course_code": "CSC 1350",
        "course_name": "Computer Science I",
        "credits": 4,
        "term": "2024 Fall Semester",
        "grade": "A",
    }],
}
# A changed record page: the grid lost its Grade column.
UNREADABLE: dict = {
    "record": [{"rows": [{"Course": "CSC 1351 - Computer Science II", "Credit Hours": "4"}]}],
}
# A readable record where every class is still in progress.
FIRST_TERM: dict = {
    "record": [{"rows": [
        {"Course": "CSC 1351 - Computer Science II", "Grade": "", "Credit Hours": "4"}
    ]}],
}


def sync(fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch, raw: dict, path: str) -> int:
    """Run one Workday sync for Jordan Example on made-up page data.

    Args:
        fake_db: In-memory database holding Jordan's saved profile.
        monkeypatch: Replaces the browser and the sync-time call.
        raw: The page grids the browser pretends to read.
        path: "sync" or "reset".

    Returns:
        The response status code.
    """
    fake_db.rows("profiles").append(copy.deepcopy(SAVED))
    monkeypatch.setattr(tiger_workday_browser, "workday_ready", lambda: True)
    monkeypatch.setattr(tiger_workday_browser, "read_workday", lambda user_id: raw)
    monkeypatch.setattr(tiger_workday, "mark_synced", lambda session: "2026-01-01T00:00:00+00:00")
    response = TestClient(app).post(
        f"/api/workday/{path}", headers={"Authorization": "Bearer token-jordan"}
    )
    return response.status_code


def test_unreadable_scrape_writes_nothing(fake_db, monkeypatch):
    """A page that can't be read is refused before anything is saved."""
    assert sync(fake_db, monkeypatch, UNREADABLE, "reset") == 502
    assert fake_db.rows("profiles") == [SAVED]
    assert fake_db.rows("schedules") == []


def test_empty_reset_keeps_courses(fake_db, monkeypatch):
    """A reset that finds no graded courses keeps the saved ones."""
    assert sync(fake_db, monkeypatch, FIRST_TERM, "reset") == 200
    assert fake_db.rows("profiles")[0]["courses"] == SAVED["courses"]


def test_no_grades_keep_gpa(fake_db, monkeypatch):
    """A sync without GPA hours keeps the saved GPA and hours."""
    assert sync(fake_db, monkeypatch, FIRST_TERM, "sync") == 200
    profile = fake_db.rows("profiles")[0]
    assert (profile["gpa"], profile["completed_credit_hours"]) == (3.5, 30)


# Made-up Jordan Example pages; their fall term is moved to always be current.
PAGES = Path(__file__).parent / "fixtures" / "workday" / "pages.json"
FALL = "2025 Fall Semester (08/23/2025-12/13/2025)"
SPRING = "2026 Spring Semester (01/12/2026-05/02/2026)"
WORKDAY_EVENTS: list[tuple] = [
    ("CSC 3102", ["Monday", "Wednesday", "Friday"], "08:30", "09:20", "Patrick F. Taylor Hall 1200", 3),
    ("CSC 3102 Lab", ["Tuesday"], "13:30", "15:20", "Patrick F. Taylor Hall 2150", None),
]


def current_pages() -> dict:
    """Load the made-up pages with the fall term running today.

    Returns:
        The page grids as the browser step would read them.
    """
    today = date.today()

    def span(start: int, end: int) -> str:
        """Date range from start to end days after today, as Workday writes it."""
        return f"({today + timedelta(start):%m/%d/%Y}-{today + timedelta(end):%m/%d/%Y})"

    text = PAGES.read_text().replace(FALL, f"2025 Fall Semester {span(-30, 30)}")
    return json.loads(text.replace(SPRING, f"2026 Spring Semester {span(60, 150)}"))


@pytest.fixture
def workday(fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Give Jordan an empty profile and a browser step returning the pages.

    Args:
        fake_db: In-memory database.
        monkeypatch: Replaces the browser and the sync-time call.

    Returns:
        The pages, which a test may edit between syncs.
    """
    pages = current_pages()
    fake_db.rows("profiles").append({"id": "jordan", "courses": []})
    monkeypatch.setattr(tiger_workday_browser, "workday_ready", lambda: True)
    monkeypatch.setattr(tiger_workday_browser, "read_workday", lambda user_id: copy.deepcopy(pages))
    monkeypatch.setattr(tiger_workday, "mark_synced", lambda session: "2026-01-01T00:00:00+00:00")
    return pages


def run(path: str = "sync") -> dict:
    """Post one sync as Jordan.

    Args:
        path: "sync" or "reset".

    Returns:
        The response body.
    """
    response = TestClient(app).post(f"/api/workday/{path}", headers=JORDAN)
    assert response.status_code == 200, response.text
    return response.json()


def term_events() -> list[tuple]:
    """List the events on Jordan's one Workday schedule.

    Returns:
        (title, days, start, end, location, credit) per event.
    """
    (schedule,) = tiger_schedules_store.list_schedules(tiger_auth.verify_token("token-jordan"))
    return [
        (e.title, e.days, e.start, e.end, e.location, getattr(e, "credit", None))
        for e in schedule.events
    ]


def test_first_sync_imports(workday: dict) -> None:
    """The first sync saves grades, courses and this term's classes."""
    body = run()
    assert (body["courses_added"], body["classes_added"], body["schedule_created"]) == (8, 2, True)
    assert term_events() == WORKDAY_EVENTS


def test_sync_again_adds_nothing(workday: dict) -> None:
    """A second sync of the same pages changes nothing."""
    run()
    body = run()
    assert (body["courses_added"], body["classes_added"]) == (0, 0)
    assert term_events() == WORKDAY_EVENTS


def test_deleted_class_stays_deleted(workday: dict) -> None:
    """A class the student deleted is not added back by the next sync."""
    run()
    session = tiger_auth.verify_token("token-jordan")
    (schedule,) = tiger_schedules_store.list_schedules(session)
    schedule.events = [e for e in schedule.events if e.title != "CSC 3102 Lab"]
    tiger_schedules_store.save_schedule(session, schedule)
    assert run()["classes_added"] == 0
    assert term_events() == WORKDAY_EVENTS[:1]
