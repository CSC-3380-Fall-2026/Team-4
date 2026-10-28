
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
    assert error.value.detail == "Enter a minimum of one course."

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
