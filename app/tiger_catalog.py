"""Course catalog endpoints backed by data/course_requirements.json."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router: APIRouter= APIRouter()

DATA_FILE = ( Path(__file__).resolve().parents[1] / "data" / "course_requirements.json" )


def fail(detail: str) -> HTTPException:
    """Build a 500 error for bad course data.

    Args:
        detail: Message describing the data problem.

    Returns:
        An HTTPException with status 500.
    """
    return HTTPException(status_code=500, detail=detail)


def read_data() -> object:
    """Read and parse the course data file.

    Returns:
        The parsed JSON contents.

    Raises:
        HTTPException: If the file is missing, unreadable, or invalid.
    """
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise fail(
            "Their is course data missing. Add data/course_requirements.json."
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise fail("Invalid course data make sure its a JSON file.")
    except OSError:
        raise fail("The course data is unreadable please fix it")


def check_course(course: object, category: str, number: int) -> dict:
    """Validate one course record and return it cleaned.

    Args:
        course: Raw course value from the data file.
        category: Name of the category containing the course.
        number: One-based position of the course in its category.

    Returns:
        The course with the four required fields stripped.

    Raises:
        HTTPException: If the record is malformed.
    """
    location = f"Course {number} in '{category}'"
    if not isinstance(course, dict):
        raise fail(f"{location} must be a object.")
    for field in ["course_code", "course_name", "category"]:
        value = course.get(field)
        if not isinstance(value, str) or not value.strip():
            raise fail(
                f"{location} needs a nonempty text value for '{field}'."
            )
    credits = course.get("credits")
    if type(credits) is not int or credits <= 0:
        raise fail(f"{location} needs a positive whole number for credits.")
    if course["category"].strip() != category.strip():
        raise fail(
            f"{location} has a category that does not match its section."
        )
    return {
        "course_code": course["course_code"].strip(),
        "course_name": course["course_name"].strip(),
        "credits": credits,
        "category": course["category"].strip(),
    }


def check_section(category: str, section: object) -> list[dict]:
    """Validate one category and return its cleaned courses.

    Args:
        category: Category name from the data file.
        section: Raw category value holding a courses list.

    Returns:
        The category's validated courses.

    Raises:
        HTTPException: If the category or any course is malformed.
    """
    if not category.strip():
        raise fail("This course category is blank please fix")
    if not isinstance(section, dict) or not isinstance(
        section.get("courses"), list
    ):
        raise fail(f"Category '{category}' needs a new courses list.")
    return [
        check_course(course, category, number)
        for number, course in enumerate(section["courses"], start=1)
    ]


def load_courses() -> list[dict]:
    """Load and validate every course from the data file.

    Returns:
        One cleaned dict per course.

    Raises:
        HTTPException: If the data file is missing or invalid.
    """
    data = read_data()
    if not isinstance(data, dict) or not isinstance(
        data.get("categories"), dict
    ):
        raise fail("Course data is missing categories.")
    courses: list[dict] = []
    for category, section in data["categories"].items():
        courses.extend(check_section(category, section))
    return courses


@router.get("/courses", tags=["Course Catalog"])
def search_courses(query: str = "", category: str = "") -> list[dict]:
    """Search courses by text and optional category.

    Args:
        query: Text matched against course code or name.
        category: Exact category name to filter by.

    Returns:
        The matching courses.
    """
    query = query.strip().lower()
    category = category.strip().lower()
    return [
        course
        for course in load_courses()
        if (
            query == ""
            or query in course["course_code"].lower()
            or query in course["course_name"].lower()
        )
        and (category == "" or category == course["category"].lower())
    ]
