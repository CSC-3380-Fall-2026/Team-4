"""Check account and profile form behaviour found in two-user testing."""

import sys
from pathlib import Path

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
