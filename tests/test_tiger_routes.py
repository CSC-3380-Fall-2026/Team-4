import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient
from tiger_app import app

client = TestClient(app)


@pytest.fixture
def member(fake_db: object) -> TestClient:
    """Provide a browser signed in as a fake student with a valid token.

    Args:
        fake_db: In-memory Supabase replacement.

    Returns:
        A test browser carrying the login cookie.
    """
    browser = TestClient(app)
    browser.cookies.set("tiger_access", "token-alice")
    return browser


def test_health_route():
    response = client.get("/health")
    assert response.status_code == 200


def test_public_page_routes():
    for path in ["/login", "/signup", "/catalog"]:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "text/html" in response.headers["content-type"]


def test_member_page_routes(member):
    for path in ["/", "/dashboard", "/schedule", "/planning", "/friends"]:
        response = member.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "text/html" in response.headers["content-type"]


def test_unknown_route_returns_404():
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404


def test_friends_page_contains_request_form(member):
    response = member.get("/friends")
    assert response.status_code == 200
    assert 'id="find-friend-form"' in response.text
    assert 'name="username"' in response.text
    assert 'type="submit"' in response.text


def test_planning_page_contains_gpa_inputs(member):
    response = member.get("/planning")
    assert response.status_code == 200
    assert 'id="target-gpa"' in response.text
    assert 'id="completed-credits"' in response.text


def test_schedule_page_contains_controls(member):
    response = member.get("/schedule")
    assert response.status_code == 200
    assert 'id="schedule-add"' in response.text
    assert 'id="schedule-edit"' in response.text


def test_login_page_has_form():
    response = client.get("/login")
    assert "<form" in response.text.lower()
    assert 'type="password"' in response.text.lower()


def test_registration_page_has_form():
    response = client.get("/signin")
    assert "<form" in response.text.lower()
    assert 'type="password"' in response.text.lower()


def test_profile_page_has_editable_fields(member):
    response = member.get("/profile")
    assert "<form" in response.text.lower()
    assert "<input" in response.text.lower()


def test_dashboard_course_checker_has_input_and_validation(member):
    response = member.get("/dashboard")
    assert response.status_code == 200
    assert 'id="prereq-course"' in response.text
    assert 'id="completed-courses"' in response.text
    assert "Check prerequisites" in response.text


def test_login_rejects_missing_credentials():
    response = client.post("/login", json={})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_signup_rejects_missing_credentials():
    response = client.post("/signup", json={})
    assert response.status_code == 422
    assert "detail" in response.json()

def test_catalog_page_contains_course_content():
    response = client.get("/catalog")
    assert response.status_code == 200
    assert "course" in response.text.lower()
