
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
