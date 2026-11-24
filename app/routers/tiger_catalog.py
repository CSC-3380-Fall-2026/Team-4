"""Course catalog page, search and prerequisite checks, backed by the files in data/."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

import tiger_auth
from models.tiger_catalog import (
    CourseResult,
    PrerequisiteRequest,
    Requirement,
)
from models.tiger_session import Session
from tiger_views import render_page

CATALOG_FILE = ( Path(__file__).resolve().parents[2] / "data" / "course_requirements.json" )
PREREQUISITE_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "course_prerequisites.json"
)

GRADE_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F": 0.0,
}


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
        with CATALOG_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise fail(
            "Their is course data missing. Add data/course_requirements.json."
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise fail("Invalid course data make sure its a JSON file.")
    except OSError:
        raise fail("The course data is unreadable please fix it")


def check_record(course: object, category: str, number: int) -> dict:
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
        check_record(course, category, number)
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


def load_prerequisites() -> dict:
    """Read the prerequisite catalog from disk.

    Returns:
        Mapping of course code to its prerequisite data.
    """
    with PREREQUISITE_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def grade_meets(grade: str, minimum: str | None) -> bool | None:
    """Compare a letter grade with a required minimum.

    Args:
        grade: The student's letter grade.
        minimum: Required letter grade, or None for any grade.

    Returns:
        True or False for a known grade, None when the grade is unknown.
    """
    if minimum is None:
        return True
    if grade not in GRADE_POINTS:
        return None
    return GRADE_POINTS[grade] >= GRADE_POINTS[minimum]


def check_requirement(
    requirement: Requirement,
    completed: dict[str, str],
    registered: set[str],
) -> tuple[bool, bool]:
    """Evaluate one any-of requirement.

    Args:
        requirement: The requirement with its options and rules.
        completed: Completed courses mapped to letter grades.
        registered: Courses currently registered for.

    Returns:
        A pair of (satisfied, unknown_grade).
    """
    minimum = requirement.get("min_grade")
    allows_registration = requirement.get("credit_or_registration", False)
    satisfied = False
    unknown = False
    for option in requirement["any_of"]:
        if option in completed:
            met = grade_meets(completed[option].upper(), minimum)
            satisfied = satisfied or bool(met)
            unknown = unknown or (met is None and minimum is not None)
        if allows_registration and option in registered:
            satisfied = True
    return satisfied, unknown


def check_prerequisites(
    course_code: str,
    completed: dict[str, str],
    registered: set[str] | None = None,
) -> CourseResult:
    """Check completed grades and current registration.

    Args:
        course_code: Course whose prerequisites are evaluated.
        completed: Completed courses mapped to letter grades.
        registered: Courses currently registered for.

    Returns:
        Which requirements are satisfied, missing, or unverifiable.

    Raises:
        ValueError: If the course is not in the catalog.
    """
    registered = registered or set()
    catalog = load_prerequisites()
    if course_code not in catalog:
        raise ValueError(f"Unsupported course: {course_code}")
    course = catalog[course_code]
    result: CourseResult = {
        "course_code": course_code,
        "satisfied": [],
        "missing": [],
        "cannot_evaluate": [],
        "eligible": False,
    }
    for requirement in course.get("requirements", []):
        met, unknown = check_requirement(requirement, completed, registered)
        text = " or ".join(requirement["any_of"])
        if met:
            result["satisfied"].append(text)
        elif unknown:
            result["cannot_evaluate"].append(
                f"Grade needs verification: {text}"
            )
        else:
            result["missing"].append(text)
    result["cannot_evaluate"].extend(course.get("unverified_requirements", []))
    result["eligible"] = (
        not result["missing"] and not result["cannot_evaluate"]
    )
    return result


router: APIRouter = APIRouter()
router.add_api_route(
    "/courses",
    search_courses,
    methods=["GET"],
    tags=["Course Catalog"],
)


@router.get("/catalog", response_class=HTMLResponse)
def catalog_page(
    request: Request,
    query: str = "",
    category: str = "",
) -> HTMLResponse:
    """Display the existing catalog search results inside shared navigation.

    Args:
        request: Browser request for the catalog.
        query: Course-code or course-name search text.
        category: Optional category selected in the form.

    Returns:
        An HTML result page with filters retained when errors occur.
    """
    session: Session | None = tiger_auth.optional_login(request)
    courses: list[dict[str, object]] = []
    categories: list[str] = []
    error: str = ""
    status_code: int = 200
    try:
        categories = sorted(
            {course["category"] for course in load_courses()}
        )
        if len(query) > 100:
            raise HTTPException(
                400, "Keep your search to 100 characters or fewer."
            )
        if category and category not in categories:
            raise HTTPException(400, "Choose a category from the dropdown.")
        courses = search_courses(query=query, category=category)
    except HTTPException as exception:
        error = (
            str(exception.detail)
            if exception.status_code == 400
            else (
                "The course catalog is temporarily unavailable. Please try again later."
            )
        )
        status_code = exception.status_code
    return render_page(
        request,
        "tiger_catalog.html",
        courses=courses,
        categories=categories,
        query=query,
        category=category,
        error=error,
        profile=tiger_auth.nav_profile(session) if session else None,
        status_code=status_code,
    )


@router.post("/courses/check-prerequisites", tags=["Course Catalog"])
def check_course(request: PrerequisiteRequest) -> CourseResult:
    """Return prerequisite status for a requested course.

    Args:
        request: Course code with completed and registered courses.

    Returns:
        The prerequisite evaluation result.

    Raises:
        HTTPException: 404 if the course is unsupported.
    """
    try:
        return check_prerequisites(
            request.course_code,
            request.completed,
            request.registered,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
