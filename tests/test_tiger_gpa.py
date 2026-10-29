
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

def test_weighted_semester_gpa():
    from tiger_models import Classes
    from datetime import datetime

    common = {
        "department": "CSC",
        "number": 1350,
        "name": "Test Course",
        "semester": "Fall 2026",
        "time": datetime(2026, 10, 28, 10, 0),
        "weekdays": ["M", "W"],
        "category": "core",
    }

    course1 = Classes(**common, grade=4.0, credit=3)
    course2 = Classes(**common, grade=2.0, credit=1)

    result = calculateGPA([course1, course2])

    assert result == pytest.approx(3.50)
def test_cumulative_gpa():
    from datetime import datetime
    from tiger_models import Classes
    from tiger_gpa import CumulativeGPARequest, calculateCumlativeGPA

    course = Classes(
        department="CSC",
        number=1350,
        name="Test Course",
        grade=4.0,
        credit=15,
        semester="Fall 2026",
        time=datetime(2026, 10, 28, 10, 0),
        weekdays=["M", "W"],
        category="core",
    )

    request = CumulativeGPARequest(
        currentGPA=3.0,
        completedCredits=60,
        classes=[course],
    )

    result = calculateCumlativeGPA(request)

    assert result == pytest.approx(3.20)
def test_required_gpa():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=3.0,
        completedCredits=60,
        plannedCredits=15,
        targetGPA=3.2,
    )

    result = calculateRequiredGPA(request)

    assert result == pytest.approx(4.0)
def test_unreachable_gpa_target():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=2.0,
        completedCredits=60,
        plannedCredits=15,
        targetGPA=4.0,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
    assert "unreachable" in error.value.detail.lower()
def test_zero_completed_credits_rejects_nonzero_gpa():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=3.0,
        completedCredits=0,
        plannedCredits=15,
        targetGPA=4.0,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
    assert "0.0" in error.value.detail
@pytest.mark.parametrize("invalid_gpa", [-1.0, 5.0, float("nan")])
def test_required_gpa_rejects_invalid_current_gpa(invalid_gpa):
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=invalid_gpa,
        completedCredits=60,
        plannedCredits=15,
        targetGPA=3.2,
    )

    with pytest.raises(HTTPException) as error:
        calculateRequiredGPA(request)

    assert error.value.status_code == 400
def test_zero_completed_credits_with_zero_gpa():
    from tiger_gpa import RequiredGPARequest, calculateRequiredGPA

    request = RequiredGPARequest(
        currentGPA=0.0,
        completedCredits=0,
        plannedCredits=15,
        targetGPA=3.5,
    )

    result = calculateRequiredGPA(request)

    assert result == pytest.approx(3.5)
