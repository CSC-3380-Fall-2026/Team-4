
import pytest

from app.tiger_prerequisites import check_prerequisites


def test_completed_prerequisite():
    result = check_prerequisites("CSC 1350", {"MATH 1550": "B"})
    assert result["eligible"] is True
    assert result["missing"] == []


def test_concurrent_enrollment():
    result = check_prerequisites("CSC 1350", {}, {"MATH 1552"})
    assert result["eligible"] is True


def test_missing_prerequisite():
    result = check_prerequisites("CSC 4330", {"CSC 3102": "B"})
    assert result["eligible"] is False
    assert result["missing"] == ["CSC 3380"]


def test_all_prerequisites_satisfied():
    result = check_prerequisites(
        "CSC 4330",
        {"CSC 3102": "B", "CSC 3380": "A"},
    )
    assert result["eligible"] is True


def test_grade_below_minimum():
    result = check_prerequisites("CSC 4101", {"CSC 3102": "D"})
    assert result["eligible"] is False
    assert "CSC 3102" in result["missing"]


def test_english_placement_needs_verification():
    result = check_prerequisites("ENGL 1001", {})
    assert result["eligible"] is False
    assert result["missing"] == []
    assert "English placement eligibility cannot be checked automatically" in (
        result["cannot_evaluate"]
    )


def test_unsupported_course():
    with pytest.raises(ValueError, match="Unsupported course"):
        check_prerequisites("CSC 9999", {})


def test_all_17_courses_have_prerequisite_records():
    from app.tiger_prerequisites import load_prerequisites

    catalog = load_prerequisites()
    assert len(catalog) == 17

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.tiger_prerequisites import router


def test_prerequisite_api_missing_course():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/courses/check-prerequisites",
        json={
            "course_code": "CSC 4330",
            "completed": {"CSC 3102": "B"}
        }
    )

    assert response.status_code == 200
    assert response.json()["missing"] == ["CSC 3380"]
    assert response.json()["eligible"] is False


def test_prerequisite_api_unsupported_course():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/courses/check-prerequisites",
        json={"course_code": "CSC 9999", "completed": {}}
    )

    assert response.status_code == 404
