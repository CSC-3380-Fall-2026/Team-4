"""Check Connor's page, Planning, account, and deployment integration work."""

from collections.abc import Iterator
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


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide a signed-out browser without real account services.

    Args:
        monkeypatch: Fixture that restores environment and application state.

    Yields:
        A test browser with no Supabase settings and no login cookie.
    """
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with TestClient(app) as browser:
        yield browser


@pytest.fixture
def client(bare: TestClient, fake_db: object) -> TestClient:
    """Provide a browser signed in as a fake student "alice".

    Args:
        bare: Signed-out browser.
        fake_db: In-memory Supabase replacement.

    Returns:
        The same browser carrying a token the fake Supabase accepts.
    """
    bare.cookies.set("tiger_access", "token-alice")
    return bare


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
def test_pages(bare: TestClient, path: str) -> None:
    """Check direct URLs and refreshes without account configuration.

    Args:
        bare: Signed-out test browser.
        path: A public page, API document, or asset URL.
    """
    for _ in range(2):
        response: httpx.Response = bare.get(path)
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
        scripts = soup.find_all("script")
    assert len(scripts) == 1
    assert scripts[0].get("type") == "module"
    assert scripts[0].get("src", "").endswith(
        "/static/js/planning.js?v=ts1"
    )
    assert not scripts[0].get_text(strip=True)
    assert (
        soup.select_one("[name=course_name]")["value"]
        == values["course_name"][0]
    )


def test_cookie(client: TestClient) -> None:
    """Ignore a forged forecast cookie instead of displaying its values.

    Args:
        client: Signed-in test browser.
    """
    client.cookies.set("tiger_forecast", "modified-forecast")
    assert "No GPA forecast yet" in client.get("/dashboard").text


def test_apis(bare: TestClient) -> None:
    """Preserve GPA API URLs and numeric request shapes alongside letter grades.

    Args:
        bare: Signed-out test browser.
    """
    courses: list[dict[str, object]] = [{"credit": 3, "grade": 4.0}] * 5
    response: httpx.Response = bare.post(
        "/calculateCumulativeGPA",
        json={
            "currentGPA": 3.0,
            "completedCredits": 60,
            "classes": courses,
        },
    )
    assert response.status_code == 200
    assert response.json() == pytest.approx(3.20)
    assert bare.post("/calculateTotalCredits", json=courses).json() == 15
    assert bare.post(
        "/calculateGPA", json=[{"credit": 3, "grade": "B-"}]
    ).json() == pytest.approx(2.7)
    assert bare.post(
        "/calculateGPA",
        json=[{"credit": 3, "grade": 4}, {"credit": 1, "grade": 2}],
    ).json() == pytest.approx(3.5)
    assert bare.post("/getClasses").status_code == 501


def test_required(bare: TestClient) -> None:
    """Check both zero-completed-credit cases from the earlier bug-fix task.

    Args:
        bare: Signed-out test browser.
    """
    values: dict[str, object] = {
        "currentGPA": 3.0,
        "completedCredits": 0,
        "plannedCredits": 15,
        "targetGPA": 3.5,
    }
    assert bare.post("/calculateRequiredGPA", json=values).status_code == 400
    values["currentGPA"] = 0.0
    response: httpx.Response = bare.post("/calculateRequiredGPA", json=values)
    assert response.status_code == 200
    assert response.json() == 3.5


def test_catalog(bare: TestClient) -> None:
    """Exercise the existing catalog through its HTML search page.

    Args:
        bare: Signed-out test browser.
    """
    assert "CSC 3380" in bare.get("/catalog?query=3380").text
    assert (
        "No matching courses" in bare.get("/catalog?query=xyz-no-course").text
    )
    assert bare.get("/catalog?category=invalid").status_code == 400


def test_accounts(bare: TestClient) -> None:
    """Keep public pages working when account settings have not been supplied.

    Args:
        bare: Signed-out test browser.
    """
    bare.get("/login")
    response: httpx.Response = bare.post(
        "/account/login",
        data={
            "csrf_token": bare.cookies["tiger_csrf"],
            "email": "student@example.com",
            "password": "test-only-password",
        },
    )
    assert response.status_code == 503
    assert "Account services are temporarily unavailable" in response.text
    assert "test-only-password" not in response.text
    assert 'value="student@example.com"' in response.text
    assert bare.get("/health").status_code == 200


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
    client.cookies.delete("tiger_access")
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
    assert response.headers["location"] == "/dashboard"
    assert client.cookies["tiger_access"] == "test-token"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "tiger_forecast" not in client.cookies
    assert response.headers["cache-control"] == "no-store"
    response = client.post(
        "/account/logout",
        data={"csrf_token": client.cookies["tiger_csrf"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "tiger_access" not in client.cookies


def test_profile(bare: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the verified account ID and reject malformed academic profile data.

    Args:
        bare: Signed-out test browser.
        monkeypatch: Fixture replacing the external Supabase bare.
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
    bare.cookies.set("tiger_access", "test-token")
    response: httpx.Response = bare.get("/profile?user_id=someone-else")
    assert response.status_code == 200
    assert "3.20" in response.text and "CSC 3380" in response.text
    backend.table.return_value.select.return_value.eq.assert_called_with(
        "id", "verified-student"
    )
    backend.postgrest.auth.assert_called_with("test-token")
    query.execute.return_value.data[0]["gpa"] = "not a GPA"
    response = bare.get("/profile")
    assert response.status_code == 200
    assert "saved academic information could not be loaded" in response.text


def test_profile_save(bare: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Save profile fields only for the verified account and reject bad input.

    Args:
        bare: Signed-out test browser.
        monkeypatch: Fixture replacing the external Supabase bare.
    """
    backend: Mock = Mock()
    backend.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="student-a", email="a@example.com", user_metadata={})
    )
    backend.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    monkeypatch.setattr(tiger_auth, "auth_client", Mock(return_value=backend))
    bare.get("/profile")
    token: str = bare.cookies.get("tiger_csrf")
    bare.cookies.set("tiger_access", "token-a")
    form: dict[str, str] = {
        "csrf_token": token,
        "username": "tigerA",
        "gpa": "3.4",
        "hours": "45",
        "courses": "CSC 1350, 4, Computer Science I",
    }
    response: httpx.Response = bare.post("/profile", data=form, follow_redirects=False)
    assert response.status_code == 303
    saved: dict[str, object] = backend.table.return_value.upsert.call_args.args[0]
    assert saved["id"] == "student-a"
    assert saved["completed_credit_hours"] == 45
    assert saved["courses"][0]["credits"] == 4
    form["gpa"] = "9"
    assert bare.post("/profile", data=form).status_code == 400
    form["csrf_token"] = "wrong"
    assert bare.post("/profile", data=form).status_code == 403


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
