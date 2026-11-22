
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from tiger_gpa import calculateGPA


def test_gpa_rejects_empty_course_list():
    """GPA calculation should reject an empty list of courses."""
    with pytest.raises(HTTPException) as error:
        calculateGPA([])

    assert error.value.status_code == 400
    assert error.value.detail == "Enter at least one course."


def test_cumulative_gpa_320_example():
    """A 3.00 GPA over 12 credits plus 3 credits at 4.0 gives 3.20."""
    from tiger_gpa import CumulativeGPARequest, calculateCumlativeGPA
    from tiger_models import Classes

    course = Classes(
        department="CSC",
        number=1350,
        name="Computer Science",
        grade=4.0,
        credit=3,
        semester="Fall",
        time="2026-11-06T10:00:00",
        weekdays=["M"],
        category="core",
        title="Computer Science",
        days=["Monday"],
        start="10:00",
        end="13:00",
    )
    request = CumulativeGPARequest(
        currentGPA=3.0,
        completedCredits=12,
        classes=[course],
    )
    assert calculateCumlativeGPA(request) == pytest.approx(3.20)


def test_required_gpa_rejects_unreachable_target():
    """A 4.0 cumulative target is impossible from 2.0 over 60 credits with 3 planned credits."""
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=2.0,
        completedCredits=60,
        plannedCredits=3,
        targetGPA=4.0,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
    assert "unreachable" in error.value.detail.lower()


def test_required_gpa_rejects_invalid_current_gpa():
    """A current GPA above 4.3 must be rejected."""
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=5.0,
        completedCredits=30,
        plannedCredits=3,
        targetGPA=3.5,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
    assert "current gpa" in error.value.detail.lower()
@pytest.mark.xfail(
    reason="Known model bug: credits depend on meeting duration",
    strict=True,
)
def test_course_credits_do_not_change_with_meeting_duration():
    from tiger_models import Classes

    course_data = {
        "department": "CSC",
        "number": 1350,
        "grade": 4.0,
        "semester": "Fall",
        "category": "core",
        "title": "Computer Science",
        "days": ["Monday"],
        "start": "10:00",
        "end": "11:00",
    }

    short_class = Classes(**course_data, credit=3)

    long_class = Classes(
        **{**course_data, "end": "13:00"},
        credit=3,
    )

    assert short_class.credit == 3
    assert long_class.credit == 3
def test_required_gpa_rejects_zero_planned_credits():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=3.0,
        completedCredits=60,
        plannedCredits=0,
        targetGPA=3.2,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
    assert "greater than zero" in error.value.detail.lower()


def test_required_gpa_with_valid_target():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=3.0,
        completedCredits=60,
        plannedCredits=15,
        targetGPA=3.2,
    )

    assert calculateRequiredGPA(request) == pytest.approx(4.0)
def test_semester_gpa_weighted_by_credits():
    from types import SimpleNamespace
    from tiger_gpa import calculateGPA

    courses = [
        SimpleNamespace(grade=4.0, credit=3),
        SimpleNamespace(grade=3.0, credit=1),
    ]

    assert calculateGPA(courses) == pytest.approx(3.75)


def test_semester_gpa_rejects_zero_credits():
    from types import SimpleNamespace
    from tiger_gpa import calculateGPA

    courses = [SimpleNamespace(grade=4.0, credit=0)]

    with pytest.raises(HTTPException) as error:
        calculateGPA(courses)

    assert error.value.status_code == 400
    assert "credit" in error.value.detail.lower()
