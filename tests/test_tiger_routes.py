import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient
from tiger_app import app

client = TestClient(app)


def test_health_route():
    response = client.get("/health")
    assert response.status_code == 200


def test_public_page_routes():
    for path in ["/", "/login", "/signin", "/dashboard", "/schedule", "/planning", "/friends", "/profile"]:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "text/html" in response.headers["content-type"]


def test_unknown_route_returns_404():
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404


def test_friends_page_contains_request_form():
    response = client.get("/friends")
    assert response.status_code == 200
    assert 'id="find-friend-form"' in response.text
    assert 'name="username"' in response.text
    assert 'type="submit"' in response.text


def test_planning_page_contains_gpa_inputs():
    response = client.get("/planning")
    assert response.status_code == 200
    assert 'id="input-targ-cum-GPA"' in response.text
    assert 'id="input-curr-credits"' in response.text


def test_schedule_page_contains_controls():
    response = client.get("/schedule")
    assert response.status_code == 200
    assert 'id="schedule-add"' in response.text
    assert 'id="schedule-edit"' in response.text


import pytest


@pytest.mark.xfail(strict=True, reason="Login form not implemented yet")
def test_login_page_has_form():
    response = client.get("/login")
    assert "<form" in response.text.lower()
    assert 'type="password"' in response.text.lower()


@pytest.mark.xfail(strict=True, reason="Registration form not implemented yet")
def test_registration_page_has_form():
    response = client.get("/signin")
    assert "<form" in response.text.lower()
    assert 'type="password"' in response.text.lower()


@pytest.mark.xfail(strict=True, reason="Profile form not implemented yet")
def test_profile_page_has_editable_fields():
    response = client.get("/profile")
    assert "<form" in response.text.lower()
    assert "<input" in response.text.lower()


def test_dashboard_course_checker_has_input_and_validation():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert 'id="prereq-course"' in response.text
    assert 'id="completed-courses"' in response.text
    assert "checkCoursePrerequisites()" in response.text
    assert "Please enter a course code." in response.text


def test_login_rejects_missing_credentials():
    response = client.post("/login", json={})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_signup_rejects_missing_credentials():
    response = client.post("/signup", json={})
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.xfail(
    strict=True,
    reason="Dedicated catalog page has not been implemented",
)
def test_catalog_page_contains_course_content():
    response = client.get("/catalog")
    assert response.status_code == 200
    assert "course" in response.text.lower()
