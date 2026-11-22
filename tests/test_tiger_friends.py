"""Check friend requests and schedule sharing under row level security."""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vercel_entry import app
from fake_supabase import FakeDatabase


def login(uid: str) -> dict[str, str]:
    """Build the bearer header the fake database accepts for a student.

    Args:
        uid: Student id.

    Returns:
        Authorization header.
    """
    return {"Authorization": f"Bearer token-{uid}"}


@pytest.fixture
def web(fake_db: FakeDatabase) -> TestClient:
    """Provide a browser plus three students with usernames.

    Args:
        fake_db: In-memory database.

    Returns:
        A test client.
    """
    for uid, name in (("alex", "AlexTiger"), ("blake", "blaketiger"), ("casey", "casey")):
        fake_db.rows("profiles").append({"id": uid, "username": name})
    return TestClient(app)


def send(web: TestClient, sender: str, username: str) -> httpx.Response:
    """Send a friend request.

    Args:
        web: Test client.
        sender: Sending student's id.
        username: Username to befriend.

    Returns:
        The response.
    """
    return web.post(
        "/api/friends/requests", json={"username": username}, headers=login(sender)
    )


def lists(web: TestClient, uid: str) -> dict:
    """Read a student's friends and requests.

    Args:
        web: Test client.
        uid: Student id.

    Returns:
        The /list response body.
    """
    return web.get("/api/friends/list", headers=login(uid)).json()


def befriend(web: TestClient) -> str:
    """Make alex and blake friends.

    Args:
        web: Test client.

    Returns:
        The friendship id.
    """
    request_id = send(web, "alex", "blaketiger").json()["request"]["id"]
    web.post(f"/api/friends/requests/{request_id}/accept", headers=login("blake"))
    return request_id


def make_schedule(web: TestClient, uid: str) -> str:
    """Create a schedule for a student.

    Args:
        web: Test client.
        uid: Owner id.

    Returns:
        The schedule id.
    """
    response = web.post(
        "/api/schedules", json={"name": "Fall", "color": "blue"}, headers=login(uid)
    )
    return response.json()["id"]


def test_request_found_despite_private_profiles(web: TestClient) -> None:
    """Find another student by username even though their profile is hidden."""
    response = send(web, "alex", "BLAKETIGER")
    assert response.status_code == 201
    assert "blaketiger" in response.json()["message"].lower()


def test_request_errors_are_clear(web: TestClient, fake_db: FakeDatabase) -> None:
    """Explain unknown names, self requests, and a missing own username."""
    assert send(web, "alex", "nobody").status_code == 404
    assert "nobody" in send(web, "alex", "nobody").json()["detail"]
    assert send(web, "alex", "alextiger").status_code == 400
    fake_db.rows("profiles").append({"id": "dana", "username": None})
    response = send(web, "dana", "blaketiger")
    assert response.status_code == 400
    assert "username" in response.json()["detail"]


def test_duplicate_requests_explained(web: TestClient) -> None:
    """Refuse repeat and reverse requests with a message for each case."""
    send(web, "alex", "blaketiger")
    again = send(web, "alex", "blaketiger")
    assert again.status_code == 409 and "already sent" in again.json()["detail"]
    reverse = send(web, "blake", "AlexTiger")
    assert reverse.status_code == 409 and "Accept it below" in reverse.json()["detail"]


def test_lists_name_the_other_student(web: TestClient) -> None:
    """Show usernames on both sides of a pending request."""
    send(web, "alex", "blaketiger")
    incoming = lists(web, "blake")["incoming_requests"]
    outgoing = lists(web, "alex")["outgoing_requests"]
    assert [row["username"] for row in incoming] == ["AlexTiger"]
    assert [row["username"] for row in outgoing] == ["blaketiger"]
    assert lists(web, "casey") == {
        "friends": [], "incoming_requests": [], "outgoing_requests": []
    }


def test_accept_makes_both_friends(web: TestClient) -> None:
    """Accepting shows each student in the other's friend list."""
    request_id = send(web, "alex", "blaketiger").json()["request"]["id"]
    assert web.post(
        f"/api/friends/requests/{request_id}/accept", headers=login("alex")
    ).status_code == 404
    assert web.post(
        f"/api/friends/requests/{request_id}/accept", headers=login("blake")
    ).status_code == 200
    assert [f["username"] for f in lists(web, "alex")["friends"]] == ["blaketiger"]
    assert [f["username"] for f in lists(web, "blake")["friends"]] == ["AlexTiger"]
    again = send(web, "blake", "alextiger")
    assert again.status_code == 409 and "already friends" in again.json()["detail"]


def test_decline_and_cancel(web: TestClient) -> None:
    """Let the recipient decline and the sender cancel, but nobody else."""
    first = send(web, "alex", "blaketiger").json()["request"]["id"]
    assert web.delete(
        f"/api/friends/requests/{first}", headers=login("casey")
    ).status_code == 404
    declined = web.delete(f"/api/friends/requests/{first}", headers=login("blake"))
    assert declined.json()["message"] == "Friend request declined."
    second = send(web, "alex", "blaketiger").json()["request"]["id"]
    canceled = web.delete(f"/api/friends/requests/{second}", headers=login("alex"))
    assert canceled.json()["message"] == "Friend request canceled."
    assert lists(web, "blake")["incoming_requests"] == []


def test_share_only_with_friends(web: TestClient) -> None:
    """Share a schedule with a friend, once, and list who can see it."""
    schedule_id = make_schedule(web, "alex")
    body = {"schedule_id": schedule_id, "friend_id": "blake"}
    assert web.post(
        "/api/friends/shares", json=body, headers=login("alex")
    ).status_code == 403
    befriend(web)
    assert web.post(
        "/api/friends/shares", json=body, headers=login("alex")
    ).status_code == 201
    web.post("/api/friends/shares", json=body, headers=login("alex"))
    shares = web.get("/api/friends/shares", headers=login("alex")).json()
    assert [(s["schedule_id"], s["username"]) for s in shares] == [
        (schedule_id, "blaketiger")
    ]
    seen = web.get("/api/friends/shared-with-me", headers=login("blake")).json()
    assert [row["schedule"]["id"] for row in seen] == [schedule_id]
    assert web.get("/api/friends/shared-with-me", headers=login("casey")).json() == []


def test_stop_sharing(web: TestClient) -> None:
    """Stop sharing hides the schedule from the friend."""
    befriend(web)
    schedule_id = make_schedule(web, "alex")
    share = web.post(
        "/api/friends/shares",
        json={"schedule_id": schedule_id, "friend_id": "blake"},
        headers=login("alex"),
    ).json()["share"]
    assert web.delete(
        f"/api/friends/shares/{share['id']}", headers=login("blake")
    ).status_code == 404
    assert web.delete(
        f"/api/friends/shares/{share['id']}", headers=login("alex")
    ).status_code == 200
    assert web.get("/api/friends/shared-with-me", headers=login("blake")).json() == []


def test_remove_friend_stops_sharing(web: TestClient, fake_db: FakeDatabase) -> None:
    """Removing a friend ends the friendship and the remover's shares."""
    friendship = befriend(web)
    schedule_id = make_schedule(web, "alex")
    web.post(
        "/api/friends/shares",
        json={"schedule_id": schedule_id, "friend_id": "blake"},
        headers=login("alex"),
    )
    assert web.delete(f"/api/friends/{friendship}", headers=login("casey")).status_code == 404
    assert web.delete(f"/api/friends/{friendship}", headers=login("alex")).status_code == 200
    assert lists(web, "blake")["friends"] == []
    assert fake_db.rows("schedule_shares") == []
    assert web.get("/api/friends/shared-with-me", headers=login("blake")).json() == []


def test_friends_api_requires_login(web: TestClient) -> None:
    """Reject every friends call without a session."""
    assert web.get("/api/friends/list").status_code == 401
    assert web.post("/api/friends/requests", json={"username": "x"}).status_code == 401
    assert web.get("/api/friends/shares").status_code == 401


def test_pages_survive_missing_name_function(
    web: TestClient, fake_db: FakeDatabase
) -> None:
    """Keep schedules and friends loading if friend_profiles() is missing."""
    befriend(web)
    fake_db.broken.add("friend_profiles")
    assert web.get("/api/schedule-data", headers=login("alex")).status_code == 200
    friends = lists(web, "alex")["friends"]
    assert [friend["username"] for friend in friends] == ["Student"]
