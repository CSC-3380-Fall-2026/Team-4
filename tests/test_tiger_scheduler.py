import os
import sys
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
