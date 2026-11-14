import os
import sys
import pytest
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient
from tiger_app import app
from tiger_scheduler import _session_data


def test_schedule_survives_reopening():
    with TestClient(app) as client:
        created = client.post(
            "/api/schedules",
            json={"name": "QA Test Schedule", "color": "blue"},
        )
        assert created.status_code == 201, created.text
        schedule_id = created.json()["id"]

        reopened = client.get("/api/schedule-data")
        assert reopened.status_code == 200
        schedules = reopened.json()["users"]
        assert any(
            schedule["id"] == schedule_id
            for user in schedules
            for schedule in user["schedules"]
        )


def test_separate_sessions_cannot_access_schedule():
    with TestClient(app) as owner, TestClient(app) as other:
        created = owner.post(
            "/api/schedules",
            json={"name": "Private QA Schedule", "color": "blue"},
        )
        assert created.status_code == 201, created.text
        schedule_id = created.json()["id"]

        other.get("/api/schedule-data")
        response = other.put(
            f"/api/schedules/{schedule_id}",
            json={"name": "Unauthorized Change", "color": "red"},
        )
        assert response.status_code == 404, response.text
@pytest.mark.xfail(reason="Known bug: overlapping classes are accepted instead of rejected", strict=True)
def test_overlapping_classes_should_be_rejected():
    with TestClient(app) as client:
        created = client.post(
            "/api/schedules",
            json={"name": "Conflict Test", "color": "blue"},
        )
        assert created.status_code == 201
        schedule_id = created.json()["id"]

        first = client.post(
            f"/api/schedules/{schedule_id}/events",
            json={
                "title": "Class A",
                "days": ["Monday"],
                "start": "10:00",
                "end": "11:00",
            },
        )
        assert first.status_code == 201, first.text

        second = client.post(
            f"/api/schedules/{schedule_id}/events",
            json={
                "title": "Class B",
                "days": ["Monday"],
                "start": "10:30",
                "end": "11:30",
            },
        )
        assert second.status_code == 409, (
            "Overlapping classes should be rejected"
        )
def test_back_to_back_classes_are_allowed():
    with TestClient(app) as client:
        created = client.post(
            "/api/schedules",
            json={"name": "Boundary Test", "color": "blue"},
        )
        assert created.status_code == 201
        schedule_id = created.json()["id"]

        for title, start, end in [
            ("Class A", "10:00", "11:00"),
            ("Class B", "11:00", "12:00"),
        ]:
            response = client.post(
                f"/api/schedules/{schedule_id}/events",
                json={
                    "title": title,
                    "days": ["Monday"],
                    "start": start,
                    "end": end,
                },
            )
            assert response.status_code == 201, response.text


@pytest.mark.xfail(
    strict=True,
    reason="Scheduler does not yet require authenticated accounts",
)
def test_unauthenticated_user_cannot_create_schedule():
    with TestClient(app) as anonymous:
        response = anonymous.post(
            "/api/schedules",
            json={"name": "Unauthorized Schedule", "color": "blue"},
        )
        assert response.status_code in (401, 403), response.text
