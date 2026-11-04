
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
