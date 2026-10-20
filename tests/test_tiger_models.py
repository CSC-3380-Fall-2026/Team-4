from pydantic import ValidationError
from app.tiger_models import Classes


def test_classes_valid_data():
    course = Classes(
        department="CSC",
        number=3380,
        name="Object Oriented Design",
        grade=95.0,
        credit=3,
        semester="Fall 2026"
    )

    assert course.department == "CSC"
    assert course.number == 3380
    assert course.name == "Object Oriented Design"
    assert course.grade == 95.0
    assert course.credit == 3
    assert course.semester == "Fall 2026"


def test_classes_missing_required_field():
    try:
        Classes(
            department="CSC",
            number=3380,
            name="Object Oriented Design",
            grade=95.0,
            credit=3
        )
        assert False, "Classes should require a semester"
    except ValidationError:
        assert True


def test_classes_invalid_number_type():
    try:
        Classes(
            department="CSC",
            number="not-a-number",
            name="Object Oriented Design",
            grade=95.0,
            credit=3,
            semester="Fall 2026"
        )
        assert False, "Classes should reject an invalid course number"
    except ValidationError:
        assert True
