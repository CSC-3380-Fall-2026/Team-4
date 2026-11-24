"""Check login gating and that student data is stored per student in Supabase."""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vercel_entry import app
import tiger_auth
from fake_supabase import FakeDatabase
from test_connor_pages import sample_plan, submit_plan
from routers.tiger_dashboard import upcoming_events
from models.tiger_schedules import Classes, Schedule, ScheduleEvent
from routers.tiger_schedules_store import to_row

PROTECTED: list[str] = [
    "/",
    "/dashboard",
    "/schedule",
    "/planning",
    "/friends",
    "/profile",
]
ZONE: ZoneInfo = ZoneInfo("America/Chicago")
EVERY_DAY: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def browser(token: str = "") -> TestClient:
    """Create a separate browser, optionally signed in.

    Args:
        token: Access token for the login cookie, or empty for signed out.

    Returns:
        A test browser with its own cookie jar.
    """
    tab: TestClient = TestClient(app)
    if token:
        tab.cookies.set("tiger_access", token)
    return tab


def add_schedule(
    db: FakeDatabase, uid: str, name: str, events: list[ScheduleEvent]
) -> None:
    """Store a schedule row the way the schedules API does.

    Args:
        db: Fake database.
        uid: Owner id.
        name: Schedule name.
        events: Events to store.
    """
    schedule: Schedule = Schedule(name=name, color="blue", events=events)
    db.rows("schedules").append(
        {
            **to_row(schedule),
            "id": schedule.id,
            "user_id": uid,
            "created_at": next(db.clock),
        }
    )


def meeting(title: str, days: list[str], start: str, end: str) -> ScheduleEvent:
    """Build a plain schedule event.

    Args:
        title: Event title.
        days: Weekday names.
        start: Start time as HH:MM.
        end: End time as HH:MM.

    Returns:
        The event.
    """
    return ScheduleEvent(title=title, days=days, start=start, end=end)


@pytest.mark.parametrize("path", PROTECTED)
def test_signed_out_redirects(fake_db: FakeDatabase, path: str) -> None:
    """Send signed-out visitors to the login page without caching.

    Args:
        fake_db: Fake Supabase.
        path: A protected page.
    """
    response: httpx.Response = browser().get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/planning", "/profile"])
def test_signed_out_posts(fake_db: FakeDatabase, path: str) -> None:
    """Refuse form posts from signed-out visitors.

    Args:
        fake_db: Fake Supabase.
        path: A protected form address.
    """
    tab: TestClient = browser()
    tab.cookies.set("tiger_csrf", "abc")
    response: httpx.Response = tab.post(
        path, data={"csrf_token": "abc"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("token", ["garbage", "token", "expired-token"])
def test_bad_token(fake_db: FakeDatabase, token: str) -> None:
    """Redirect invalid tokens and delete the stale cookie.

    Args:
        fake_db: Fake Supabase, which rejects tokens not issued by it.
        token: A token Supabase would not verify.
    """
    tab: TestClient = browser(token)
    response: httpx.Response = tab.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert 'tiger_access="";' in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_no_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect when Supabase answers without a user, as for an expired token.

    Args:
        monkeypatch: Fixture replacing the Supabase client.
    """
    backend: Mock = Mock()
    backend.auth.get_user.return_value = SimpleNamespace(user=None)
    monkeypatch.setattr(tiger_auth, "auth_client", Mock(return_value=backend))
    response: httpx.Response = browser("expired").get(
        "/planning", follow_redirects=False
    )
    assert response.status_code == 303
    backend.auth.get_user.assert_called_once_with("expired")


@pytest.mark.parametrize("path", PROTECTED[1:])
def test_valid_token(fake_db: FakeDatabase, path: str) -> None:
    """Show pages to a verified student, uncached.

    Args:
        fake_db: Fake Supabase.
        path: A protected page.
    """
    response: httpx.Response = browser("token-alice").get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "Log out" in response.text


def test_bearer_token(fake_db: FakeDatabase) -> None:
    """Accept an Authorization bearer token instead of the cookie.

    Args:
        fake_db: Fake Supabase.
    """
    response: httpx.Response = browser().get(
        "/dashboard", headers={"Authorization": "Bearer token-alice"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/login", "/signup", "/catalog", "/health", "/favicon.ico"],
)
def test_public_pages(fake_db: FakeDatabase, path: str) -> None:
    """Keep account, catalog and health pages open to everyone.

    Args:
        fake_db: Fake Supabase.
        path: A public address.
    """
    assert browser().get(path).status_code == 200


def test_signed_out_nav(fake_db: FakeDatabase) -> None:
    """Hide account links and private tabs from signed-out visitors.

    Args:
        fake_db: Fake Supabase.
    """
    page: str = browser().get("/login").text
    assert "Log out" not in page and "View profile" not in page
    assert 'href="/dashboard" class="nav-link' not in page


def test_forecast_per_user(fake_db: FakeDatabase) -> None:
    """Save each forecast under its owner and keep students separate.

    Args:
        fake_db: Fake Supabase.
    """
    alice, bob = browser("token-alice"), browser("token-bob")
    response: httpx.Response = submit_plan(alice, sample_plan())
    assert response.status_code == 200
    assert "tiger_forecast" not in response.headers.get("set-cookie", "")
    rows = fake_db.rows("forecasts")
    assert [row["user_id"] for row in rows] == ["alice"]
    assert rows[0]["result"]["cumulative_gpa"] == pytest.approx(3.2)
    assert "No GPA forecast yet" in bob.get("/dashboard").text
    mine: BeautifulSoup = BeautifulSoup(alice.get("/dashboard").text, "html.parser")
    assert mine.select_one("#dashboard-cumulative").get_text(strip=True) == "3.20"
    values: dict[str, object] = dict(sample_plan(), course_grade=["B"] * 5)
    submit_plan(bob, values)
    assert sorted(row["user_id"] for row in rows) == ["alice", "bob"]
    again: BeautifulSoup = BeautifulSoup(
        browser("token-alice").get("/dashboard").text, "html.parser"
    )
    assert again.select_one("#dashboard-cumulative").get_text(strip=True) == "3.20"


def test_forecast_update(fake_db: FakeDatabase) -> None:
    """Replace a student's earlier forecast instead of adding another row.

    Args:
        fake_db: Fake Supabase.
    """
    tab: TestClient = browser("token-alice")
    submit_plan(tab, sample_plan())
    submit_plan(tab, dict(sample_plan(), course_grade=["B"] * 5))
    rows = fake_db.rows("forecasts")
    assert len(rows) == 1
    assert rows[0]["result"]["semester_gpa"] == pytest.approx(3.0)


def test_save_failure(fake_db: FakeDatabase) -> None:
    """Show the calculation and a clear note when saving fails.

    Args:
        fake_db: Fake Supabase.
    """
    fake_db.broken.add("forecasts")
    tab: TestClient = browser("token-alice")
    response: httpx.Response = submit_plan(tab, sample_plan())
    assert response.status_code == 200
    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#cumulative-result").get_text(strip=True) == "3.20"
    assert "could not be saved" in response.text
    dash: httpx.Response = tab.get("/dashboard")
    assert dash.status_code == 200
    assert "No GPA forecast yet" in dash.text


def test_saved_note_hidden(fake_db: FakeDatabase) -> None:
    """Omit the failure note when the forecast was stored.

    Args:
        fake_db: Fake Supabase.
    """
    response = submit_plan(browser("token-alice"), sample_plan())
    assert "could not be saved" not in response.text


def test_events_from_schedules(fake_db: FakeDatabase) -> None:
    """Show the student's own upcoming meetings, soonest first, at most six.

    Args:
        fake_db: Fake Supabase.
    """
    add_schedule(
        fake_db,
        "alice",
        "Fall plan",
        [
            meeting("Morning lab", EVERY_DAY, "00:00", "00:30"),
            meeting("Night talk", EVERY_DAY, "23:58", "23:59"),
            Classes(
                title="CSC 3380",
                days=["Monday"],
                start="10:00",
                end="11:00",
                department="CSC",
                number=3380,
                grade=0.0,
                semester="Fall 2026",
                category="Core",
                credit=3,
            ),
        ],
    )
    add_schedule(
        fake_db, "bob", "Bob only", [meeting("Bob event", EVERY_DAY, "12:00", "13:00")]
    )
    page: BeautifulSoup = BeautifulSoup(
        browser("token-alice").get("/dashboard").text, "html.parser"
    )
    items = page.select("#upcoming-events li")
    stamps = [item.select_one("time")["datetime"] for item in items]
    assert len(items) == 6 and stamps == sorted(stamps)
    assert "Bob event" not in page.get_text()
    selected: str = page.select_one("#selected-schedule").get_text(" ", strip=True)
    assert "Fall plan" in selected and "Fall 2026" in selected
    assert "Courses 1" in selected and "Credit hours 3" in selected


def test_dashboard_empty(fake_db: FakeDatabase) -> None:
    """Show honest empty states for a student with no saved data.

    Args:
        fake_db: Fake Supabase.
    """
    page: str = browser("token-carol").get("/dashboard").text
    for phrase in ("No schedule selected", "No upcoming events", "No GPA forecast yet"):
        assert phrase in page


def test_dashboard_profile(fake_db: FakeDatabase) -> None:
    """Show GPA and completed hours from the profile row.

    Args:
        fake_db: Fake Supabase.
    """
    fake_db.rows("profiles").append(
        {"id": "alice", "gpa": 3.4, "completed_credit_hours": 45}
    )
    page: str = browser("token-alice").get("/dashboard").text
    assert "Current GPA 3.40" in page and "45 completed credit hours" in page


def test_dashboard_storage_down(fake_db: FakeDatabase) -> None:
    """Keep the dashboard working when every table fails.

    Args:
        fake_db: Fake Supabase.
    """
    fake_db.broken.update({"forecasts", "schedules", "profiles"})
    response: httpx.Response = browser("token-alice").get("/dashboard")
    assert response.status_code == 200
    assert "No upcoming events" in response.text


def test_occurrences() -> None:
    """Place weekly meetings after the current moment in Chicago time."""
    now: datetime = datetime(2026, 11, 23, 9, 0, tzinfo=ZONE)
    schedule: Schedule = Schedule(
        name="Plan",
        color="blue",
        events=[
            meeting("Early", ["Monday"], "08:00", "09:00"),
            meeting("Late", ["Monday", "Wednesday"], "10:00", "11:00"),
        ],
    )
    found = upcoming_events([schedule], now)
    assert [(item.title, item.starts_at.day) for item in found[:3]] == [
        ("Late", 23),
        ("Late", 25),
        ("Early", 30),
    ]
    assert len(found) == 6
    assert all(item.starts_at.tzinfo is not None for item in found)


def test_semester_uses_campus_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """At 10 pm on May 31 in Baton Rouge it is still spring, though UTC says June.

    Args:
        monkeypatch: Fixture that freezes the clock.
    """
    from routers import tiger_schedules_store

    instant = datetime(2026, 6, 1, 3, 0, tzinfo=ZoneInfo("UTC"))

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        @classmethod
        def today(cls):
            return instant.date()  # a server clock running on UTC, as on Vercel

    monkeypatch.setattr(tiger_schedules_store, "datetime", Frozen)
    monkeypatch.setattr(tiger_schedules_store, "date", Frozen)
    assert tiger_schedules_store.current_semester() == "Spring 2026"


def course(code: str, credit: int, day: str) -> Classes:
    """Build a class entry as the Schedule page stores it.

    Args:
        code: Course code, such as "CSC 3380".
        credit: Credit hours.
        day: Meeting day.

    Returns:
        The class.
    """
    department, number = code.split()
    return Classes(
        title=code, days=[day], start="10:00", end="11:00", department=department,
        number=int(number), grade=0.0, semester="Fall 2026", category="Core", credit=credit,
    )


def load_into_plan(fake_db: FakeDatabase, events: list[ScheduleEvent]) -> httpx.Response:
    """Save a schedule for alice and press "Load courses" on the planner.

    Args:
        fake_db: Fake Supabase.
        events: The schedule's events.

    Returns:
        The planner response.
    """
    add_schedule(fake_db, "alice", "Fall plan", events)
    schedule_id = fake_db.rows("schedules")[-1]["id"]
    values = {**sample_plan(), "action": "load_schedule", "schedule_id": schedule_id}
    return submit_plan(browser("token-alice"), values)


def test_planner_loads_schedule_courses(fake_db: FakeDatabase) -> None:
    """Loading a schedule fills one row per course with its credits."""
    response = load_into_plan(
        fake_db, [course("CSC 3380", 3, "Monday"), course("MATH 2057", 4, "Tuesday")]
    )
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert [f["value"] for f in soup.select("[name=course_name]")] == ["CSC 3380", "MATH 2057"]
    assert [f["value"] for f in soup.select("[name=course_credit]")] == ["3", "4"]


def test_planner_duplicate_course_keeps_rows(fake_db: FakeDatabase) -> None:
    """A schedule listing a course twice is refused and the typed rows stay."""
    response = load_into_plan(
        fake_db, [course("CSC 3380", 3, "Monday"), course("CSC 3380", 3, "Tuesday")]
    )
    assert response.status_code == 409
    assert "multiple entries for the same course" in response.text
    soup = BeautifulSoup(response.text, "html.parser")
    names = [f["value"] for f in soup.select("[name=course_name]")]
    assert names == sample_plan()["course_name"]


def test_failed_target_not_saved(fake_db: FakeDatabase) -> None:
    """A plan whose target cannot be calculated is shown but not saved."""
    tab = browser("token-alice")
    values = {**sample_plan(), "target_gpa": "4.3"}
    assert submit_plan(tab, values).status_code == 400
    assert fake_db.rows("forecasts") == []
    assert "No GPA forecast yet" in tab.get("/dashboard").text


def test_dashboard_events_from_first_schedule(fake_db: FakeDatabase) -> None:
    """Upcoming events come from one schedule, not every alternative mixed."""
    add_schedule(fake_db, "alice", "Plan A", [meeting("Plan A class", EVERY_DAY, "23:58", "23:59")])
    add_schedule(fake_db, "alice", "Plan B", [meeting("Plan B class", EVERY_DAY, "23:58", "23:59")])
    page = browser("token-alice").get("/dashboard").text
    assert "Plan A class" in page
    assert "Plan B class" not in page


def test_login_sets_refresh_cookie(fake_db: FakeDatabase) -> None:
    """Signing in stores both tokens in HTTP-only cookies."""
    fake_db.users["alice@lsu.edu"] = {
        "id": "alice", "email": "alice@lsu.edu", "password": "12345678", "meta": {}
    }
    tab = browser()
    tab.get("/login")
    response = tab.post(
        "/account/login",
        data={"csrf_token": tab.cookies["tiger_csrf"], "email": "alice@lsu.edu",
              "password": "12345678"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("tiger_access=token-alice") and "HttpOnly" in c for c in cookies)
    assert any(c.startswith("tiger_refresh=refresh-alice") and "HttpOnly" in c for c in cookies)


@pytest.mark.parametrize("path", ["/dashboard", "/api/schedule-data"])
def test_expired_access_is_refreshed(fake_db: FakeDatabase, path: str) -> None:
    """After the one-hour token expires, pages and the API renew the session."""
    tab = browser("expired-token")
    tab.cookies.set("tiger_refresh", "refresh-alice")
    response = tab.get(path, follow_redirects=False)
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("tiger_access=token-alice") for c in cookies)
    assert any(c.startswith("tiger_refresh=refresh-alice") for c in cookies)


def test_bad_refresh_still_signs_out(fake_db: FakeDatabase) -> None:
    """A refresh token Supabase refuses leads to the login page or a 401."""
    tab = browser()
    tab.cookies.set("tiger_refresh", "stolen")
    assert tab.get("/dashboard", follow_redirects=False).headers["location"] == "/login"
    assert tab.get("/api/schedule-data").status_code == 401


def test_logout_clears_both_cookies(fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    """Logging out removes the access and refresh cookies."""
    monkeypatch.setattr(tiger_auth, "logout", Mock(return_value=True))
    tab = browser("token-alice")
    tab.cookies.set("tiger_refresh", "refresh-alice")
    tab.get("/login")
    response = tab.post(
        "/account/logout", data={"csrf_token": tab.cookies["tiger_csrf"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    cleared = response.headers.get_list("set-cookie")
    for name in ("tiger_access", "tiger_refresh"):
        assert any(c.startswith(f'{name}=""') and "Max-Age=0" in c for c in cleared)


def test_login_form_has_no_dead_options(fake_db: FakeDatabase) -> None:
    """An unticked "Keep me logged in" box, and no "Forgot password?" link."""
    page = BeautifulSoup(browser().get("/login").text, "html.parser")
    box = page.find("input", attrs={"name": "remember"})
    assert box is not None and box.get("type") == "checkbox"
    assert not box.has_attr("checked")
    assert "Keep me logged in" in page.text
    assert "Forgot password" not in page.text


def log_in(fake_db: FakeDatabase, remember: bool) -> tuple[TestClient, str]:
    """Sign alice in through the form, with or without "Keep me logged in".

    Args:
        fake_db: Fake Supabase holding alice's account.
        remember: Whether the box is ticked.

    Returns:
        The browser and the refresh cookie header it was sent.
    """
    fake_db.users["alice@lsu.edu"] = {
        "id": "alice", "email": "alice@lsu.edu", "password": "12345678", "meta": {}
    }
    tab = browser()
    tab.get("/login")
    form = {"csrf_token": tab.cookies["tiger_csrf"], "email": "alice@lsu.edu",
            "password": "12345678"}
    if remember:
        form["remember"] = "on"
    response = tab.post("/account/login", data=form, follow_redirects=False)
    cookies = response.headers.get_list("set-cookie")
    return tab, next(c for c in cookies if c.startswith("tiger_refresh="))


def renewed_refresh(tab: TestClient) -> str:
    """Let the access token expire and return the renewed refresh cookie header.

    Args:
        tab: A signed-in browser.

    Returns:
        The refresh cookie header set while renewing.
    """
    tab.cookies.set("tiger_access", "expired-token")
    cookies = tab.get("/api/schedule-data").headers.get_list("set-cookie")
    return next(c for c in cookies if c.startswith("tiger_refresh="))


def test_unticked_login_ends_with_browser(fake_db: FakeDatabase) -> None:
    """Without "Keep me logged in" the refresh cookie lasts one browser session."""
    tab, cookie = log_in(fake_db, remember=False)
    assert "Max-Age" not in cookie and "expires" not in cookie.lower()
    renewed = renewed_refresh(tab)
    assert "Max-Age" not in renewed and "expires" not in renewed.lower()


def test_ticked_login_lasts_30_days(fake_db: FakeDatabase) -> None:
    """With "Keep me logged in" the refresh cookie lasts 30 days, also once renewed."""
    tab, cookie = log_in(fake_db, remember=True)
    assert "Max-Age=2592000" in cookie
    assert "Max-Age=2592000" in renewed_refresh(tab)


def test_crash_still_renews_cookies(fake_db: FakeDatabase) -> None:
    """A server error on the renewing request still hands over the new tokens."""
    tab = TestClient(app, raise_server_exceptions=False)
    tab.cookies.set("tiger_access", "expired-token")
    tab.cookies.set("tiger_refresh", "refresh-alice")
    fake_db.broken.add("schedules")
    response = tab.get("/api/schedule-data")
    assert response.status_code == 500
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("tiger_access=token-alice") for c in cookies)
    assert any(c.startswith("tiger_refresh=refresh-alice") for c in cookies)
