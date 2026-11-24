"""Check account and profile form behaviour found in two-user testing."""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vercel_entry import app
from fake_supabase import FakeDatabase


def browser(token: str = "") -> TestClient:
    """Create a browser, optionally signed in.

    Args:
        token: Access token for the login cookie.

    Returns:
        A test browser with its own cookies.
    """
    tab = TestClient(app)
    if token:
        tab.cookies.set("tiger_access", token)
    return tab


def form_token(tab: TestClient, path: str) -> str:
    """Load a page and return its form token.

    Args:
        tab: Test browser.
        path: Page holding a form.

    Returns:
        The CSRF token from the cookie.
    """
    tab.get(path)
    return tab.cookies.get("tiger_csrf")


def test_signup_needs_long_password(fake_db: FakeDatabase) -> None:
    """Refuse a short password before contacting the account service."""
    tab = browser()
    response = tab.post(
        "/account/signup",
        data={
            "csrf_token": form_token(tab, "/signup"),
            "email": "short@lsu.edu",
            "password": "abc",
            "confirm_password": "abc",
        },
    )
    assert response.status_code == 400
    assert "at least 8 characters" in response.text


def test_profile_error_keeps_typing(fake_db: FakeDatabase) -> None:
    """Show what the student typed after a validation error."""
    tab = browser("token-casey")
    response = tab.post(
        "/profile",
        data={
            "csrf_token": form_token(tab, "/profile"),
            "username": "caseyv",
            "gpa": "4.7",
            "hours": "30",
            "courses": "CSC 1350, 4, Computer Science I",
        },
    )
    assert response.status_code == 400
    assert "GPA must be between" in response.text
    assert 'value="caseyv"' in response.text
    assert 'value="4.7"' in response.text
    assert "CSC 1350, 4, Computer Science I" in response.text


def test_profile_gpa_not_a_number(fake_db: FakeDatabase) -> None:
    """Explain a non-numeric GPA in plain words."""
    tab = browser("token-casey")
    response = tab.post(
        "/profile",
        data={"csrf_token": form_token(tab, "/profile"), "gpa": "three"},
    )
    assert response.status_code == 400
    assert "GPA must be a number" in response.text
    assert "could not convert" not in response.text


def test_planning_starts_from_profile(fake_db: FakeDatabase) -> None:
    """Fill Planning with the GPA and hours saved on the profile."""
    fake_db.rows("profiles").append(
        {"id": "casey", "gpa": 3.2, "completed_credit_hours": 45}
    )
    page = browser("token-casey").get("/planning").text
    assert 'value="3.20"' in page
    assert 'value="45"' in page


def test_upload_limit_under_vercel_cap(fake_db: FakeDatabase) -> None:
    """Refuse a PDF over 4 MB with a clear message; Vercel drops bodies over 4.5 MB."""
    tab = browser("token-casey")
    response = tab.post(
        "/profile/transcript",
        data={"csrf_token": form_token(tab, "/profile")},
        files={"transcript": ("t.pdf", b"%PDF" + b"0" * (4 * 1024 * 1024), "application/pdf")},
    )
    assert response.status_code == 400
    assert "That PDF is too large (4 MB limit)." in response.text


def sign_in_failing(monkeypatch, error: Exception) -> str:
    """Submit the login form while the account service raises an error.

    Args:
        monkeypatch: Fixture replacing the account service client.
        error: What the sign-in call raises.

    Returns:
        The page shown to the student.
    """
    import tiger_auth
    from types import SimpleNamespace

    def fail(_credentials):
        raise error

    service = SimpleNamespace(auth=SimpleNamespace(sign_in_with_password=fail))
    monkeypatch.setattr(tiger_auth, "auth_client", lambda: service)
    tab = browser()
    return tab.post(
        "/account/login",
        data={
            "csrf_token": form_token(tab, "/login"),
            "email": "jordan@lsu.edu",
            "password": "12345678",
        },
    ).text


def test_login_rate_limit_message(monkeypatch) -> None:
    """A Supabase 429 says to wait, not that the password is wrong."""
    from supabase_auth.errors import AuthApiError

    page = sign_in_failing(
        monkeypatch, AuthApiError("Request rate limit reached", 429, "over_request_rate_limit")
    )
    assert "Too many sign-ins, try again in a minute" in page
    assert "Check your email and password" not in page


def test_login_outage_not_wrong_password(monkeypatch) -> None:
    """An unexpected failure is not reported as a wrong password."""
    page = sign_in_failing(monkeypatch, ConnectionError("network down"))
    assert "Check your email and password" not in page
    assert "try again" in page.lower()


def test_login_wrong_password_message(monkeypatch) -> None:
    """Supabase's invalid-credentials answer keeps the usual message."""
    from supabase_auth.errors import AuthApiError

    page = sign_in_failing(
        monkeypatch, AuthApiError("Invalid login credentials", 400, "invalid_credentials")
    )
    assert "Check your email and password" in page


def sign_up(username: str, email: str = "dana@lsu.edu") -> "httpx.Response":
    """Submit the signup form.

    Args:
        username: Chosen username.
        email: Account email; its local part becomes the fake user id.

    Returns:
        The response.
    """
    tab = browser()
    return tab.post(
        "/account/signup",
        data={
            "csrf_token": form_token(tab, "/signup"),
            "full_name": "Dana Example",
            "username": username,
            "email": email,
            "password": "12345678",
            "confirm_password": "12345678",
            "terms": "on",
        },
    )


def find(fake_db: FakeDatabase, username: str) -> int:
    """Have student alex send a friend request to a username.

    Args:
        fake_db: Fake Supabase.
        username: Username to look for.

    Returns:
        The HTTP status of the request.
    """
    fake_db.rows("profiles").append({"id": "alex", "username": "AlexTiger"})
    return browser().post(
        "/api/friends/requests",
        json={"username": username},
        headers={"Authorization": "Bearer token-alex"},
    ).status_code


def test_signup_username_found_by_friends(fake_db: FakeDatabase) -> None:
    """A fresh student is found by the username they chose at signup."""
    response = sign_up("dana_t")
    assert response.status_code == 200, response.text
    assert fake_db.users["dana@lsu.edu"]["meta"] == {
        "username": "dana_t", "full_name": "Dana Example"
    }
    assert find(fake_db, "dana_t") == 201


def test_signup_username_claimed_at_first_sign_in(fake_db: FakeDatabase) -> None:
    """With email confirmation on, the username lands on the first sign-in."""
    fake_db.confirm_email = True
    assert sign_up("dana_t").status_code == 200
    tab = browser()
    tab.post(
        "/account/login",
        data={
            "csrf_token": form_token(tab, "/login"),
            "email": "dana@lsu.edu",
            "password": "12345678",
        },
    )
    assert find(fake_db, "dana_t") == 201


@pytest.mark.parametrize("username", ["", "ab", "has space", "x" * 41, "dash-ed"])
def test_signup_bad_username(fake_db: FakeDatabase, username: str) -> None:
    """Refuse a username friends could not search for, before any account exists."""
    response = sign_up(username)
    assert response.status_code == 400
    assert "3 to 40 letters, numbers, or underscores" in response.text
    assert fake_db.users == {}


def test_signup_taken_username(fake_db: FakeDatabase) -> None:
    """Refuse a username another student has, ignoring case."""
    fake_db.rows("profiles").append({"id": "casey", "username": "Dana_T"})
    response = sign_up("dana_t")
    assert response.status_code == 409
    assert "already taken" in response.text
    assert 'value="dana_t"' in response.text
    assert fake_db.users == {}


@pytest.mark.parametrize("username", ["has space", "ab", "dash-ed"])
def test_profile_username_rules(fake_db: FakeDatabase, username: str) -> None:
    """The profile form holds usernames to the same rule as signup.

    Args:
        fake_db: In-memory database.
        username: A username signup would refuse.
    """
    from routers.tiger_accounts import BAD_USERNAME

    tab = browser("token-casey")
    response = tab.post(
        "/profile",
        data={"csrf_token": form_token(tab, "/profile"), "username": username},
    )
    assert response.status_code == 400
    assert BAD_USERNAME in response.text


@pytest.mark.parametrize("line", ["CSC 1350, 4,", "CSC 1350, 4, ", "CSC 1350, 4"])
def test_course_line_without_name(line: str) -> None:
    """A course line with no name is named after its code.

    Args:
        line: A course line whose name was left out.
    """
    from routers.tiger_profiles_parsing import parse_line

    course = parse_line(line)
    assert (course.course_code, course.credits, course.course_name) == ("CSC 1350", 4, "CSC 1350")


def test_profile_save_keeps_terms(fake_db: FakeDatabase) -> None:
    """Saving the form unchanged keeps each course's term and grade.

    Args:
        fake_db: In-memory database holding Jordan Example's courses.
    """
    courses = [
        {"course_code": "MATH 1550", "course_name": "Calculus I", "credits": 5,
         "term": "2024 Fall Semester", "grade": "F"},
        {"course_code": "MATH 1550", "course_name": "Calculus I", "credits": 5,
         "term": "2025 Spring Semester", "grade": "B"},
    ]
    fake_db.rows("profiles").append({"id": "jordan", "courses": [dict(c) for c in courses]})
    tab = browser("token-jordan")
    response = tab.post(
        "/profile",
        data={
            "csrf_token": form_token(tab, "/profile"),
            "courses": "MATH 1550, 5, Calculus I\nMATH 1550, 5, Calculus I",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert fake_db.rows("profiles")[0]["courses"] == courses
