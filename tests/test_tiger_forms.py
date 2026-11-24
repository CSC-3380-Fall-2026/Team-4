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
