"""Check that a Workday sync never saves over data it could not read."""

import copy

import pytest
from fastapi.testclient import TestClient

from fake_supabase import FakeDatabase
from routers import tiger_workday, tiger_workday_browser
from tiger_app import app

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
