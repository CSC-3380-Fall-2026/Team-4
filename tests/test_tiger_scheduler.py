import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient
from tiger_app import app

BLUE = {"name": "QA Schedule", "color": "blue"}


def login(user_id: str) -> dict[str, str]:
    """Build the bearer header the fake database accepts for a student."""
    return {"Authorization": f"Bearer token-{user_id}"}


@pytest.fixture
def web(fake_db):
    """Provide a test browser wired to the in-memory database."""
    with TestClient(app) as browser:
        yield browser


def make_schedule(web, user_id="alice", body=BLUE) -> str:
    """Create a schedule and return its id."""
    response = web.post("/api/schedules", json=body, headers=login(user_id))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_event(web, schedule_id, start, end, user_id="alice"):
    """Post a Monday event and return the response."""
    return web.post(
        f"/api/schedules/{schedule_id}/events",
        json={"title": f"E{start}", "days": ["Monday"], "start": start, "end": end},
        headers=login(user_id),
    )


def test_signed_out_requests_are_rejected(web):
    assert web.get("/api/schedule-data").status_code == 401
    assert web.post("/api/schedules", json=BLUE).status_code == 401
    assert web.get("/api/course-presets").status_code == 401
    assert web.post("/api/shared-free-time", json={}).status_code in (401, 422)


def test_new_student_gets_empty_page(web):
    body = web.get("/api/schedule-data", headers=login("alice")).json()
    assert body["currentUserId"] == "alice"
    assert [user["id"] for user in body["users"]] == ["alice"]
    assert body["users"][0]["schedules"] == []
    assert body["metrics"] == {}


def test_schedule_persists_across_requests(web):
    schedule_id = make_schedule(web)
    web.put(
        f"/api/schedules/{schedule_id}",
        json={"name": "Renamed", "color": "red"},
        headers=login("alice"),
    )
    assert add_event(web, schedule_id, "10:00", "11:00").status_code == 201

    page = web.get("/api/schedule-data", headers=login("alice")).json()
    schedule = page["users"][0]["schedules"][0]
    assert schedule["id"] == schedule_id
    assert (schedule["name"], schedule["color"]) == ("Renamed", "red")
    assert schedule["events"][0]["title"] == "E10:00"
    assert page["metrics"][schedule_id]["totalHours"] == 1


def test_event_update_and_delete_persist(web):
    schedule_id = make_schedule(web)
    event_id = add_event(web, schedule_id, "10:00", "11:00").json()["id"]
    path = f"/api/schedules/{schedule_id}/events/{event_id}"
    changed = web.put(
        path,
        json={"title": "Moved", "days": ["Friday"], "start": "13:00", "end": "14:00"},
        headers=login("alice"),
    )
    assert changed.status_code == 200, changed.text
    events = web.get("/api/schedule-data", headers=login("alice")).json()
    assert events["users"][0]["schedules"][0]["events"][0]["title"] == "Moved"

    assert web.delete(path, headers=login("alice")).status_code == 204
    events = web.get("/api/schedule-data", headers=login("alice")).json()
    assert events["users"][0]["schedules"][0]["events"] == []


def test_delete_schedule_keeps_one(web):
    first = make_schedule(web)
    assert web.delete(f"/api/schedules/{first}", headers=login("alice")).status_code == 409
    second = make_schedule(web, body={"name": "Two", "color": "green"})
    assert web.delete(f"/api/schedules/{first}", headers=login("alice")).status_code == 204
    page = web.get("/api/schedule-data", headers=login("alice")).json()
    assert [s["id"] for s in page["users"][0]["schedules"]] == [second]


def test_students_never_see_each_other(web):
    schedule_id = make_schedule(web, "alice")

    page = web.get("/api/schedule-data", headers=login("bob")).json()
    assert [user["id"] for user in page["users"]] == ["bob"]
    assert page["users"][0]["schedules"] == []

    other = {"name": "Hacked", "color": "red"}
    path = f"/api/schedules/{schedule_id}"
    assert web.put(path, json=other, headers=login("bob")).status_code == 404
    assert add_event(web, schedule_id, "10:00", "11:00", "bob").status_code == 404
    make_schedule(web, "bob")
    make_schedule(web, "bob", {"name": "Second", "color": "green"})
    assert web.delete(path, headers=login("bob")).status_code == 404


def test_overlapping_classes_should_be_rejected(web):
    schedule_id = make_schedule(web)
    assert add_event(web, schedule_id, "10:00", "11:00").status_code == 201
    assert add_event(web, schedule_id, "10:30", "11:30").status_code == 409


def test_back_to_back_classes_are_allowed(web):
    schedule_id = make_schedule(web)
    assert add_event(web, schedule_id, "10:00", "11:00").status_code == 201
    assert add_event(web, schedule_id, "11:00", "12:00").status_code == 201


def test_course_presets_use_only_catalog_fields(web):
    response = web.get("/api/course-presets", headers=login("alice"))
    assert response.status_code == 200
    first = response.json()[0]
    assert first["credit"] > 0
    assert set(first) == {
        "courseId", "title", "courseName", "department",
        "number", "credit", "category", "semester",
    }


def test_add_course_stores_class_with_chosen_times(web):
    schedule_id = make_schedule(web)
    preset = web.get("/api/course-presets", headers=login("alice")).json()[0]
    added = web.post(
        f"/api/schedules/{schedule_id}/courses",
        json={
            "courseId": preset["courseId"], "title": "ignored",
            "days": ["Tuesday"], "start": "09:00", "end": "10:15",
        },
        headers=login("alice"),
    )
    assert added.status_code == 201, added.text
    assert added.json()["title"] == preset["title"]
    assert added.json()["credit"] == preset["credit"]

    page = web.get("/api/schedule-data", headers=login("alice")).json()
    stored = page["users"][0]["schedules"][0]["events"][0]
    assert stored["department"] == preset["department"]

    missing = web.post(
        f"/api/schedules/{schedule_id}/courses",
        json={"courseId": "NOPE 0000", "title": "x", "days": ["Monday"],
              "start": "09:00", "end": "10:00"},
        headers=login("alice"),
    )
    assert missing.status_code == 404


def befriend(db, left, right, status="accepted"):
    """Insert a friendship row."""
    db.rows("friendships").append(
        {"id": f"{left}-{right}", "requester_id": left,
         "addressee_id": right, "status": status}
    )


def share(db, schedule_id, owner, friend):
    """Insert a schedule share row."""
    db.rows("schedule_shares").append(
        {"id": f"{schedule_id}-{friend}", "schedule_id": schedule_id,
         "owner_id": owner, "friend_id": friend}
    )


def test_shared_schedule_visible_only_to_accepted_friend(web, fake_db):
    schedule_id = make_schedule(web, "alice")
    add_event(web, schedule_id, "10:00", "11:00", "alice")
    fake_db.rows("profiles").append({"id": "alice", "username": "alice_u"})
    share(fake_db, schedule_id, "alice", "bob")
    share(fake_db, schedule_id, "alice", "carol")
    befriend(fake_db, "alice", "bob", "accepted")
    befriend(fake_db, "alice", "carol", "pending")

    bob = web.get("/api/schedule-data", headers=login("bob")).json()
    assert [user["id"] for user in bob["users"]] == ["bob", "alice"]
    friend = bob["users"][1]
    assert friend["username"] == "alice_u"
    assert friend["schedules"][0]["id"] == schedule_id

    free = web.post(
        "/api/shared-free-time",
        json={"friendUsername": "alice_u", "startTime": "08:00",
              "endTime": "12:00", "minimumDuration": 30},
        headers=login("bob"),
    )
    assert free.status_code == 200, free.text
    assert free.json()["days"][0] == {
        "day": "Monday",
        "periods": [{"start": "08:00", "end": "10:00"},
                    {"start": "11:00", "end": "12:00"}],
    }

    carol = web.get("/api/schedule-data", headers=login("carol")).json()
    assert [user["id"] for user in carol["users"]] == ["carol"]
    dave = web.get("/api/schedule-data", headers=login("dave")).json()
    assert [user["id"] for user in dave["users"]] == ["dave"]


def test_unreadable_friend_username_gets_neutral_label(web, fake_db):
    first = make_schedule(web, "alice")
    second = make_schedule(web, "erin")
    for owner, schedule_id in (("alice", first), ("erin", second)):
        share(fake_db, schedule_id, owner, "bob")
        befriend(fake_db, owner, "bob")
    users = web.get("/api/schedule-data", headers=login("bob")).json()["users"]
    assert [user["username"] for user in users[1:]] == ["Friend", "Friend 2"]
    assert all(user["email"] == "" for user in users[1:])


def test_schedule_names_must_be_unique(web):
    """Refuse a second schedule, or a rename, that reuses a name."""
    first = make_schedule(web)
    copy = web.post(
        "/api/schedules", json={"name": "qa schedule", "color": "red"}, headers=login("alice")
    )
    assert copy.status_code == 409
    assert "already have a schedule" in copy.json()["detail"]
    other = make_schedule(web, "alice", {"name": "Spring", "color": "green"})
    clash = web.put(f"/api/schedules/{other}", json=BLUE, headers=login("alice"))
    assert clash.status_code == 409
    same = web.put(f"/api/schedules/{first}", json=BLUE, headers=login("alice"))
    assert same.status_code == 200
    assert make_schedule(web, "bob") != first


def test_name_race_is_409_not_500(web, monkeypatch):
    """Two creates racing past the name check: the database index answers 409."""
    from routers import tiger_schedules

    first = make_schedule(web)
    other = make_schedule(web, "alice", {"name": "Spring", "color": "green"})
    monkeypatch.setattr(tiger_schedules, "check_name", lambda *args: None)
    copy = web.post("/api/schedules", json=BLUE, headers=login("alice"))
    assert copy.status_code == 409
    assert copy.json()["detail"] == 'You already have a schedule named "QA Schedule".'
    clash = web.put(f"/api/schedules/{other}", json=BLUE, headers=login("alice"))
    assert clash.status_code == 409
    assert web.put(f"/api/schedules/{first}", json=BLUE, headers=login("alice")).status_code == 200


def test_shared_schedules_load_in_one_query(web, fake_db):
    """Three shared schedules cost one schedules query, not two calls each."""
    names = ("Fall", "Spring", "Summer")
    ids = [make_schedule(web, "alice", {"name": n, "color": "blue"}) for n in names]
    for schedule_id in ids:
        share(fake_db, schedule_id, "alice", "bob")
    befriend(fake_db, "alice", "bob")
    fake_db.calls.clear()
    page = web.get("/api/schedule-data", headers=login("bob")).json()
    assert [s["id"] for s in page["users"][1]["schedules"]] == ids
    assert fake_db.calls.count("schedules") == 2  # bob's own, then all shared
    assert fake_db.calls.count("friendships") == 0  # the read policy checks friendship
