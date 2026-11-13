"""Check Connor's page, Planning, account, and deployment integration work."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode
import sys
import tomllib

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vercel_entry import app
import tiger_auth
from models.tiger_dashboard import DashboardData, ScheduleSummary, UpcomingEvent


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide an isolated browser without contacting real account services.

    Args:
        monkeypatch: Fixture that restores environment and application state.

    Yields:
        A test browser with a test-only forecast signing key.
    """
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-only-forecast-signing-value")
    monkeypatch.delattr(app.state, "dashboard_provider", raising=False)
    with TestClient(app) as browser:
        yield browser


def sample_plan() -> dict[str, object]:
    """Build the required 60-credit plus 15-credit acceptance example.

    Returns:
        HTML form values whose cumulative result should be 3.20.
    """
    return {
        "current_gpa": "3.0",
        "completed_credits": "60",
        "target_gpa": "3.20",
        "course_name": [
            "CSC 2259",
            "CSC 2262",
            "CSC 3102",
            "CSC 3380",
            "CSC 3501",
        ],
        "course_credit": ["3"] * 5,
        "course_grade": ["A"] * 5,
        "action": "calculate",
    }


def submit_plan(
    client: TestClient, values: dict[str, object]
) -> httpx.Response:
    """Submit form data with the same token a browser receives.

    Args:
        client: Isolated test browser.
        values: Input values, including repeated course fields.

    Returns:
        The Planning response.
    """
    client.get("/planning")
    fields: dict[str, object] = dict(
        values, csrf_token=client.cookies["tiger_csrf"]
    )
    return client.post(
        "/planning",
        content=urlencode(fields, doseq=True),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/schedule",
        "/planning",
        "/friends",
        "/profile",
        "/login",
        "/signup",
        "/catalog",
        "/docs",
        "/openapi.json",
        "/health",
        "/static/css/app.css",
        "/static/tiger_workspace.css",
        "/favicon.ico",
    ],
)
def test_pages(client: TestClient, path: str) -> None:
    """Check direct URLs and refreshes without account configuration.

    Args:
        client: Isolated test browser.
        path: A supported page, API document, or asset URL.
    """
    for _ in range(2):
        response: httpx.Response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.content


def test_navigation(client: TestClient) -> None:
    """Check shared navigation destinations and preserved URL aliases.

    Args:
        client: Isolated test browser.
    """
    soup: BeautifulSoup = BeautifulSoup(
        client.get("/dashboard").text, "html.parser"
    )
    for link in soup.select("nav a[href]"):
        assert client.get(link["href"]).status_code == 200
    for original, destination in (("/", "/dashboard"), ("/signin", "/signup")):
        response: httpx.Response = client.get(original, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == destination
    assert not soup.select("script[src]")


def test_acceptance(client: TestClient) -> None:
    """Check the assigned GPA example and its dashboard connection.

    Args:
        client: Isolated test browser.
    """
    response: httpx.Response = submit_plan(client, sample_plan())
    assert response.status_code == 200

    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#semester-result").get_text(strip=True) == "4.00"
    assert soup.select_one("#cumulative-result").get_text(strip=True) == "3.20"
    assert soup.select_one("#required-result").get_text(strip=True) == "4.00"

    dashboard: BeautifulSoup = BeautifulSoup(
        client.get("/dashboard").text, "html.parser"
    )
    assert (
        dashboard.select_one("#dashboard-cumulative").get_text(strip=True)
        == "3.20"
    )

    values: dict[str, object] = sample_plan()
    values["course_grade"] = ["B"] * 5
    soup = BeautifulSoup(submit_plan(client, values).text, "html.parser")
    assert soup.select_one("#semester-result").get_text(strip=True) == "3.00"
    assert soup.select_one("#cumulative-result").get_text(strip=True) == "3.00"

def test_unreachable(client: TestClient) -> None:
    """Keep all entered information when the target is unreachable.

    Args:
        client: Isolated test browser.
    """
    values: dict[str, object] = sample_plan()
    values["target_gpa"] = "4.3"
    response: httpx.Response = submit_plan(client, values)
    assert response.status_code == 400
    assert "highest possible cumulative GPA is 3.26" in response.text
    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#cumulative-result").get_text(strip=True) =="3.20"
    assert soup.select_one("[name=target_gpa]")["value"] == "4.3"
    assert [
        field["value"] for field in soup.select("[name=course_name]")
    ] == values["course_name"]
    assert len(soup.select("[name=course_grade] option[selected]")) == 5


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("current_gpa", "NaN", "finite number"),
        ("current_gpa", "4.4", "between 0.0 and 4.3"),
        ("completed_credits", "0", "must be 0.0 when no credits"),
        ("completed_credits", "-1", "cannot be negative"),
        ("completed_credits", "2.5", "whole credit hours"),
        ("course_credit", ["0"] * 5, "greater than zero"),
        ("course_credit", ["2.5"] * 5, "whole credit hours"),
        ("course_grade", ["Z"] * 5, "choose an expected letter grade"),
        ("target_gpa", "Infinity", "finite number"),
        ("target_gpa", "-1", "between 0.0 and 4.3"),
    ],
)
def test_validation(
    client: TestClient, field: str, value: object, message: str
) -> None:
    """Reject invalid inputs without dropping their form values.

    Args:
        client: Isolated test browser.
        field: Form field to change.
        value: Invalid field value.
        message: Expected useful explanation.
    """
    values: dict[str, object] = sample_plan()
    values[field] = value
    response: httpx.Response = submit_plan(client, values)
    assert response.status_code == 400
    assert message in response.text
    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    control = soup.select_one(f"[name={field}]")
    expected: object = value[0] if isinstance(value, list) else value
    if control.name == "select":
        assert control.select_one("option[selected]")["value"] == expected
    else:
        assert control["value"] == expected


def test_rows(client: TestClient) -> None:
    """Add and remove course rows while preserving grade and history entries.

    Args:
        client: Isolated test browser.
    """
    values: dict[str, object] = sample_plan()
    values["action"] = "add"
    soup: BeautifulSoup = BeautifulSoup(
        submit_plan(client, values).text, "html.parser"
    )
    assert len(soup.select("[name=course_name]")) == 6
    assert soup.select_one("[name=current_gpa]")["value"] == "3.0"
    values["action"] = "remove:1"
    soup = BeautifulSoup(submit_plan(client, values).text, "html.parser")
    assert len(soup.select("[name=course_name]")) == 4
    assert "CSC 2262" not in str(soup.select_one("#planning-form"))


def test_empty(client: TestClient) -> None:
    """Reject empty plans and show real empty dashboard sections.

    Args:
        client: Isolated test browser.
    """
    response: httpx.Response = submit_plan(
        client,
        {
            "current_gpa": "0",
            "completed_credits": "0",
            "course_name": "",
            "course_credit": "",
            "course_grade": "",
        },
    )
    assert response.status_code == 400
    assert "Enter at least one course" in response.text
    page: str = client.get("/dashboard").text
    for phrase in (
        "No schedule selected",
        "No GPA forecast yet",
        "No upcoming events",
    ):
        assert phrase in page


def test_newstudent(client: TestClient) -> None:
    """Allow a student with no previous credits to calculate a forecast.

    Args:
        client: Isolated test browser.
    """
    values: dict[str, object] = sample_plan()
    values.update(current_gpa="0", completed_credits="0", target_gpa="3.5")
    response: httpx.Response = submit_plan(client, values)
    assert response.status_code == 200
    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#cumulative-result").get_text(strip=True) == "4.00"
    assert soup.select_one("#required-result").get_text(strip=True) == "3.50"
    values.update(
        current_gpa="4.3",
        completed_credits="60",
        target_gpa="4.3",
        course_grade=["A+"] * 5,
    )
    assert submit_plan(client, values).status_code == 200


def test_csrf(client: TestClient) -> None:
    """Reject missing or malformed form tokens without a server exception.

    Args:
        client: Isolated test browser.
    """
    client.get("/planning")
    for token in ("", "invalid", "é"):
        response: httpx.Response = client.post(
            "/planning", data={"csrf_token": token, "current_gpa": "3.1"}
        )
        assert response.status_code == 403
        assert 'value="3.1"' in response.text


def test_escaping(client: TestClient) -> None:
    """Escape user-entered course text when redisplaying a plan.

    Args:
        client: Isolated test browser.
    """
    values: dict[str, object] = sample_plan()
    values["course_name"] = ['<script>alert("x")</script>'] * 5
    response: httpx.Response = submit_plan(client, values)
    soup: BeautifulSoup = BeautifulSoup(response.text, "html.parser")
    assert not soup.find("script")
    assert (
        soup.select_one("[name=course_name]")["value"]
        == values["course_name"][0]
    )


def test_cookie(client: TestClient) -> None:
    """Ignore a modified forecast cookie instead of displaying its values.

    Args:
        client: Isolated test browser.
    """
    submit_plan(client, sample_plan())
    client.cookies.clear()
    client.cookies.set("tiger_forecast", "modified-forecast")
    assert "No GPA forecast yet" in client.get("/dashboard").text


def test_supplied(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Render supplied schedule data and only future events in time order.

    Args:
        client: Isolated test browser.
        monkeypatch: Fixture used to provide request-specific dashboard records.
    """
    now: datetime = datetime.now(timezone.utc)
    records: DashboardData = DashboardData(
        selected=ScheduleSummary(
            name="Spring plan",
            semester="Spring 2027",
            credit_hours=15,
            course_count=5,
        ),
        events=[
            UpcomingEvent(
                title="Later meeting", starts_at=now + timedelta(days=2)
            ),
            UpcomingEvent(
                title="Past meeting", starts_at=now - timedelta(days=2)
            ),
            UpcomingEvent(
                title="Next meeting", starts_at=now + timedelta(days=1)
            ),
        ],
    )
    monkeypatch.setattr(
        app.state,
        "dashboard_provider",
        Mock(return_value=records),
        raising=False,
    )
    for path in ("/dashboard", "/schedule"):
        page: str = client.get(path).text
        assert "Spring plan" in page
        assert "Past meeting" not in page
        assert page.index("Next meeting") < page.index("Later meeting")
    assert len(records.events) == 3


def test_apis(client: TestClient) -> None:
    """Preserve GPA API URLs and numeric request shapes alongside letter grades.

    Args:
        client: Isolated test browser.
    """
    courses: list[dict[str, object]] = [{"credit": 3, "grade": 4.0}] * 5
    response: httpx.Response = client.post(
        "/calculateCumulativeGPA",
        json={
            "currentGPA": 3.0,
            "completedCredits": 60,
            "classes": courses,
        },
    )
    assert response.status_code == 200
    assert response.json() == pytest.approx(3.20)
    assert client.post("/calculateTotalCredits", json=courses).json() == 15
    assert client.post(
        "/calculateGPA", json=[{"credit": 3, "grade": "B-"}]
    ).json() == pytest.approx(2.7)
    assert client.post(
        "/calculateGPA",
        json=[{"credit": 3, "grade": 4}, {"credit": 1, "grade": 2}],
    ).json() == pytest.approx(3.5)
    assert client.post("/getClasses").status_code == 501


def test_required(client: TestClient) -> None:
    """Check both zero-completed-credit cases from the earlier bug-fix task.

    Args:
        client: Isolated test browser.
    """
    values: dict[str, object] = {
        "currentGPA": 3.0,
        "completedCredits": 0,
        "plannedCredits": 15,
        "targetGPA": 3.5,
    }
    assert client.post("/calculateRequiredGPA", json=values).status_code == 400
    values["currentGPA"] = 0.0
    response: httpx.Response = client.post("/calculateRequiredGPA", json=values)
    assert response.status_code == 200
    assert response.json() == 3.5


def test_catalog(client: TestClient) -> None:
    """Exercise the existing catalog through its HTML search page.

    Args:
        client: Isolated test browser.
    """
    assert "CSC 3380" in client.get("/catalog?query=3380").text
    assert (
        "No matching courses" in client.get("/catalog?query=xyz-no-course").text
    )
    assert client.get("/catalog?category=invalid").status_code == 400


def test_accounts(client: TestClient) -> None:
    """Keep public pages working when account settings have not been supplied.

    Args:
        client: Isolated test browser.
    """
    client.get("/login")
    response: httpx.Response = client.post(
        "/account/login",
        data={
            "csrf_token": client.cookies["tiger_csrf"],
            "email": "student@example.com",
            "password": "test-only-password",
        },
    )
    assert response.status_code == 503
    assert "Account services are temporarily unavailable" in response.text
    assert "test-only-password" not in response.text
    assert 'value="student@example.com"' in response.text
    assert client.get("/health").status_code == 200


def test_accountflow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check login cookies and logout clearing without using a real account.

    Args:
        client: Isolated test browser.
        monkeypatch: Fixture replacing only external account operations.
    """
    monkeypatch.setattr(
        tiger_auth, "login", Mock(return_value=("test-token", True))
    )
    monkeypatch.setattr(tiger_auth, "logout", Mock(return_value=True))
    submit_plan(client, sample_plan())
    client.get("/login")
    response: httpx.Response = client.post(
        "/account/login",
        data={
            "csrf_token": client.cookies["tiger_csrf"],
            "email": "student@example.com",
            "password": "test-only-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"
    assert client.cookies["tiger_access"] == "test-token"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "tiger_forecast" not in client.cookies
    response = client.post(
        "/account/logout",
        data={"csrf_token": client.cookies["tiger_csrf"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "tiger_access" not in client.cookies


def test_profile(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the verified account ID and reject malformed academic profile data.

    Args:
        client: Isolated test browser.
        monkeypatch: Fixture replacing the external Supabase client.
    """
    backend: Mock = Mock()
    backend.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="verified-student",
            email="student@example.com",
            user_metadata={},
        )
    )
    query: Mock = (
        backend.table.return_value.select.return_value.eq.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(
        data=[
            {
                "id": "verified-student",
                "username": "Student",
                "gpa": "3.20",
                "courses": [
                    {
                        "course_code": "CSC 3380",
                        "course_name": "Design",
                        "credits": 3,
                    }
                ],
            }
        ]
    )
    monkeypatch.setattr(tiger_auth, "auth_client", Mock(return_value=backend))
    client.cookies.set("tiger_access", "test-token")
    response: httpx.Response = client.get("/profile?user_id=someone-else")
    assert response.status_code == 200
    assert "3.20" in response.text and "CSC 3380" in response.text
    backend.table.return_value.select.return_value.eq.assert_called_with(
        "id", "verified-student"
    )
    backend.postgrest.auth.assert_called_with("test-token")
    query.execute.return_value.data[0]["gpa"] = "not a GPA"
    response = client.get("/profile")
    assert response.status_code == 200
    assert "Academic information could not be loaded" in response.text


def test_entrypoint() -> None:
    """Check that the Vercel module exists and resolves to the tested app.

    Returns:
        Nothing; assertions fail when the deployment entrypoint drifts.
    """
    root: Path = Path(__file__).resolve().parents[1]
    config: dict[str, object] = tomllib.loads(
        (root / "pyproject.toml").read_text()
    )
    assert config["tool"]["vercel"]["entrypoint"] == "vercel_entry:app"
    assert (root / "vercel_entry.py").is_file()
    assert (root / "app/static/css/app.css").is_file()
    assert "Tiger_login.html" not in {
        path.name for path in (root / "app/templates").iterdir()
    }
    assert (root / "app/templates/tiger_login.html").is_file()
