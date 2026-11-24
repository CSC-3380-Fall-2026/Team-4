"""Check the Workday parser on made-up pages.

Student "Jordan Example"; every course, term and grade here is invented.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from models.tiger_workday import ProfileCourse as WorkdayCourse
from routers.tiger_workday_parsing import parse_workday, term_gpas

FIXTURES = Path(__file__).parent / "fixtures" / "workday"
FALL_DAY = date(2025, 10, 1)


def test_empty_pages_give_empty_data() -> None:
    """Pages without grids parse to empty data."""
    data = parse_workday({"courses": [], "record": [], "progress": []}, FALL_DAY)
    assert data.gpa is None
    assert data.completed_credit_hours == 0
    assert data.courses == []
    assert data.term == ""
    assert data.sections == []


def load_pages() -> dict:
    """Return the made-up Workday pages as the page script reads them."""
    return json.loads((FIXTURES / "pages.json").read_text())


def course_rows(data) -> list[tuple[str, str, str, int, str]]:
    """List each parsed course as (term, code, name, credits, grade)."""
    return [(c.term, c.course_code, c.course_name, c.credits, c.grade) for c in data.courses]


def test_graded_courses_by_term_oldest_first() -> None:
    """Graded courses are grouped by term, oldest term first."""
    data = parse_workday(load_pages(), FALL_DAY)
    rows = [row for row in course_rows(data) if row[0] != "Transfer Credit"]
    assert rows == [
        ("2024 Fall Semester", "CSC 1350", "Computer Science I", 4, "A"),
        ("2024 Fall Semester", "ENGL 1001", "English Composition", 3, "A-"),
        ("2024 Fall Semester", "BIOL 1001", "General Biology", 3, "F"),
        ("2025 Spring Semester", "CSC 1351", "Computer Science II", 4, "B+"),
        ("2025 Spring Semester", "MATH 1552", "Analytic Geometry and Calculus II", 4, "C"),
        ("2025 Spring Semester", "PHIL 1000", "Introduction to Philosophy", 3, "W"),
    ]


def test_transfer_credit_is_its_own_first_term_counted_once() -> None:
    """Transfer credit comes first and each course appears once."""
    data = parse_workday(load_pages(), FALL_DAY)
    assert course_rows(data)[:3] == [
        ("Transfer Credit", "MATH 1550", "Analytic Geometry and Calculus I", 5, ""),
        ("Transfer Credit", "HIST 2055", "United States History", 3, ""),
        ("2024 Fall Semester", "CSC 1350", "Computer Science I", 4, "A"),
    ]
    assert len(data.courses) == 8


def test_gpa_and_hours_from_earned_grade_points() -> None:
    """GPA and hours come from the earned grade points."""
    # 48.30 points over 18 GPA hours (F counts, W, transfer and in-progress do not).
    data = parse_workday(load_pages(), FALL_DAY)
    assert data.gpa == 2.683
    assert data.completed_credit_hours == 18


def test_term_gpas_from_saved_courses_with_grade_scale() -> None:
    """Term GPAs use the LSU grade scale."""
    # Fall: (4.0*4 + 3.7*3 + 0*3) / 10; Spring: (3.3*4 + 2.0*4) / 8, W left out.
    data = parse_workday(load_pages(), FALL_DAY)
    assert term_gpas(data.courses) == {
        "2024 Fall Semester": 2.71,
        "2025 Spring Semester": 2.65,
    }


def test_term_gpas_of_no_courses_is_empty() -> None:
    """No courses give no term GPAs."""
    assert term_gpas([]) == {}


def test_term_gpas_skip_zero_credit_courses() -> None:
    """A zero-credit course does not make a term GPA."""
    seminar = WorkdayCourse(
        course_code="UNIV 1001", course_name="First-Year Seminar", credits=0,
        term="2024 Fall Semester", grade="A",
    )
    assert term_gpas([seminar]) == {}


def test_current_term_is_the_first_one_not_yet_over() -> None:
    """The current term is the first one that has not ended."""
    pages = load_pages()
    assert parse_workday(pages, date(2025, 10, 1)).term == "2025 Fall Semester"
    assert parse_workday(pages, date(2025, 12, 13)).term == "2025 Fall Semester"
    assert parse_workday(pages, date(2025, 12, 20)).term == "2026 Spring Semester"
    assert parse_workday(pages, date(2026, 8, 1)).term == "2026 Spring Semester"


def test_current_term_does_not_depend_on_page_order() -> None:
    """The current term is found whatever order the grids are in."""
    pages = load_pages()
    pages["courses"].reverse()
    assert parse_workday(pages, date(2025, 10, 1)).term == "2025 Fall Semester"


def section_named(data, section: str):
    """Find a parsed section by its Workday name."""
    return next(part for part in data.sections if part.section == section)


def test_lecture_section_ready_for_a_schedule_event() -> None:
    """A lecture section has everything a schedule event needs."""
    data = parse_workday(load_pages(), FALL_DAY)
    lecture = section_named(data, "CSC 3102-001 - Advanced Data Structures")
    assert lecture.model_dump() == {
        "course_code": "CSC 3102",
        "course_name": "Advanced Data Structures",
        "credits": 3,
        "section": "CSC 3102-001 - Advanced Data Structures",
        "format": "Lecture",
        "status": "Registered",
        "dropped": False,
        "days": ["Monday", "Wednesday", "Friday"],
        "start": "08:30",
        "end": "09:20",
        "location": "Patrick F. Taylor Hall 1200",
    }


def test_odd_time_formats_become_24_hour() -> None:
    """Lower-case and noon times become 24-hour times."""
    data = parse_workday(load_pages(), FALL_DAY)
    lab = section_named(data, "CSC 3102-L01 - Advanced Data Structures")
    assert (lab.format, lab.days, lab.start, lab.end) == ("Lab", ["Tuesday"], "13:30", "15:20")
    noon = section_named(data, "ENGL 2000-012 - English Composition II")
    assert (noon.days, noon.start, noon.end) == (["Tuesday", "Thursday"], "12:00", "13:20")


def test_online_section_has_no_meeting_time() -> None:
    """An online section has no days, times or room."""
    data = parse_workday(load_pages(), FALL_DAY)
    online = section_named(data, "MATH 2090-940 - Differential Equations and Linear Algebra")
    assert (online.days, online.start, online.end, online.location) == ([], None, None, "")
    assert online.credits == 4
    assert online.dropped is False


def test_dropped_and_withdrawn_sections_are_flagged() -> None:
    """Dropped and withdrawn sections are marked dropped."""
    data = parse_workday(load_pages(), FALL_DAY)
    flags = {part.course_code: part.dropped for part in data.sections}
    assert flags["ENGL 2000"] is True
    assert flags["HIST 2057"] is True
    assert flags["CSC 3102"] is False


def test_only_the_current_terms_enrolled_sections_in_page_order() -> None:
    """Only the current term's enrolled sections are kept, in page order."""
    data = parse_workday(load_pages(), FALL_DAY)
    assert [part.section for part in data.sections] == [
        "CSC 3102-001 - Advanced Data Structures",
        "CSC 3102-L01 - Advanced Data Structures",
        "MATH 2090-940 - Differential Equations and Linear Algebra",
        "ENGL 2000-012 - English Composition II",
        "HIST 2057-002 - Modern World History",
    ]
    spring = parse_workday(load_pages(), date(2026, 1, 20))
    assert [part.course_code for part in spring.sections] == ["CSC 3380"]


EXTRACT_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "workday-extract.js"


def run_extract(*pages: str) -> list:
    """Run the page script on local fixture pages in headless Chromium.

    Args:
        pages: Fixture file names.

    Returns:
        What the script returned on each page.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    script = EXTRACT_JS.read_text(encoding="utf-8")
    with sync_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except sync_api.Error:
            pytest.skip("Chromium for Playwright is not installed.")
        page = browser.new_page()
        results = []
        for name in pages:
            page.goto((FIXTURES / name).resolve().as_uri())
            results.append(page.evaluate(script))
        browser.close()
    return results


def test_extract_js_reads_the_three_workday_pages() -> None:
    """The page script reads the three saved Workday pages."""
    courses, record, progress = run_extract("courses.html", "record.html", "progress.html")
    expected = load_pages()
    assert courses == expected["courses"]
    assert record == expected["record"]
    assert progress == expected["progress"]


def test_extract_js_on_a_page_without_grids() -> None:
    """The page script returns no grids for a page without any."""
    assert run_extract("empty.html") == [[]]


# ---- review fixes: rows and cells the live Workday may show ----

FALL = "2025 Fall Semester (08/23/2025-12/13/2025)"


def fall_sections(*rows: dict) -> list:
    """Parse enrolled-course rows of the fall term into sections."""
    raw = {"courses": [{"semester": FALL, "title": "My Enrolled Courses", "rows": list(rows)}]}
    return parse_workday(raw, FALL_DAY).sections


def meeting(pattern: str, **cells: str) -> dict:
    """Build one enrolled-course row with a meeting pattern."""
    return {
        "Course Listing": "CSC 3102 - Advanced Data Structures", "Credit Hours": "3",
        "Section": "CSC 3102-001 - Advanced Data Structures", "Instructional Format": "Lecture",
        "Meeting Patterns": pattern, "Registration Status": "Registered", **cells,
    }


def test_continuation_row_is_a_meeting_of_the_course_above() -> None:
    """A row without a course listing belongs to the course above."""
    lecture = meeting("Monday Wednesday | 9:00 AM - 9:50 AM | Lockett 1")
    recitation = meeting(
        "Thursday | 3:00 PM - 3:50 PM | Lockett 5", **{"Course Listing": "", "Credit Hours": "",
        "Section": "CSC 3102-R01 - Advanced Data Structures", "Instructional Format": "Recitation"},
    )
    sections = fall_sections(lecture, recitation)
    assert [(s.course_code, s.course_name, s.credits, s.format, s.days, s.start, s.end) for s in sections] == [
        ("CSC 3102", "Advanced Data Structures", 3, "Lecture", ["Monday", "Wednesday"], "09:00", "09:50"),
        ("CSC 3102", "Advanced Data Structures", 0, "Recitation", ["Thursday"], "15:00", "15:50"),
    ]


def fall_record(*rows: dict) -> dict:
    """Build record and progress grids for graded fall rows."""
    progress = [{"Registrations Used": row["Course"], "Academic Period": FALL} for row in rows]
    return {
        "record": [{"semester": None, "title": "Course History", "rows": list(rows)}],
        "progress": [{"semester": None, "title": "", "rows": progress}],
    }


def graded(course: str, grade: str, hours: str, points: str) -> dict:
    """Build one graded record row."""
    return {"Course": course, "Grade": grade, "Credit Hours": hours, "Earned Grade Points": points}


def test_fractional_credits_round_half_up_in_courses_and_totals() -> None:
    """Fractional credits round half up on courses and sections."""
    # Courses get whole credits (0.5 -> 1, 2.5 -> 3); GPA divides 9.5 points by the real 3.0 hours.
    raw = fall_record(
        graded("MUS 1001 - Ensemble", "A", "0.5", "2.0"),
        graded("KIN 1500 - Fitness", "B", "2.5", "7.5"),
    )
    data = parse_workday(raw, FALL_DAY)
    assert [(c.course_code, c.credits) for c in data.courses] == [("MUS 1001", 1), ("KIN 1500", 3)]
    assert data.completed_credit_hours == 3
    assert data.gpa == 3.167
    assert term_gpas(data.courses) == {"2025 Fall Semester": 3.25}
    lab = fall_sections(meeting("Tuesday | 1:00 PM - 2:00 PM | Lab", **{"Credit Hours": "1.5"}))
    assert lab[0].credits == 2


def test_shared_am_pm_and_backwards_times() -> None:
    """A shared AM/PM suffix applies to both times; backwards times are dropped."""
    times = [
        (s.start, s.end) for s in fall_sections(
            meeting("Monday | 9:00-10:20 AM | A"),
            meeting("Monday | 11:00-12:15 PM | B"),
            meeting("Monday | 1:00-2:15 PM | C"),
            meeting("Monday | 10:00 PM - 12:00 AM | D"),
        )
    ]
    assert times == [("09:00", "10:20"), ("11:00", "12:15"), ("13:00", "14:15"), (None, None)]


def test_day_lists_with_separators_and_abbreviations() -> None:
    """Day lists in many spellings are read."""
    patterns = [
        "Monday, Wednesday", "Mon/Wed/Fri", "M W F", "MWF", "TTh", "Tue Thu", "TR",
        "Tu, Th", "MTWThF", "Sat", "TBA",
    ]
    days = [s.days for s in fall_sections(*(meeting(f"{p} | 9:00 AM - 9:50 AM | X") for p in patterns))]
    assert days == [
        ["Monday", "Wednesday"],
        ["Monday", "Wednesday", "Friday"],
        ["Monday", "Wednesday", "Friday"],
        ["Monday", "Wednesday", "Friday"],
        ["Tuesday", "Thursday"],
        ["Tuesday", "Thursday"],
        ["Tuesday", "Thursday"],
        ["Tuesday", "Thursday"],
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        ["Saturday"],
        [],
    ]


def test_grades_with_spaces_count() -> None:
    """Grades padded with spaces still count."""
    raw = fall_record(graded("CSC 1350 - Computer Science I", " A ", "4", "16.0"),
                      graded("CSC 2259 - Discrete Structures", "  ", "3", ""))
    data = parse_workday(raw, FALL_DAY)
    assert [(c.course_code, c.grade) for c in data.courses] == [("CSC 1350", "A")]
    saved = WorkdayCourse(course_code="CSC 1350", course_name="CS I", credits=4, term="T", grade=" B ")
    assert term_gpas([saved]) == {"T": 3.0}


def test_malformed_numbers_skip_the_value_not_the_sync() -> None:
    """A malformed number skips that value, not the sync."""
    raw = fall_record(
        graded("CSC 1350 - Computer Science I", "A", "4", "16.0"),
        graded("MATH 1550 - Calculus I", "B", "nan", "15.0"),
        graded("ENGL 1001 - Composition", "C", "-3", "6.0"),
        graded("BIOL 1001 - Biology", "B", "3", "inf"),
    )
    raw["courses"] = [{"semester": FALL, "title": "My Enrolled Courses", "rows": [
        meeting("Monday | 9:00 AM - 9:50 AM | X", **{"Credit Hours": "-3"})]}]
    data = parse_workday(raw, FALL_DAY)
    assert [(c.course_code, c.credits) for c in data.courses] == [("CSC 1350", 4), ("BIOL 1001", 3)]
    assert (data.gpa, data.completed_credit_hours) == (4.0, 4)
    assert data.sections[0].credits == 0


def test_term_gpas_leave_out_unknown_terms() -> None:
    """Courses without a known term have no term GPA."""
    unknown = WorkdayCourse(course_code="CSC 1350", course_name="CS I", credits=4,
                            term="Unknown term", grade="A")
    known = WorkdayCourse(course_code="CSC 1351", course_name="CS II", credits=4,
                          term="2025 Spring Semester", grade="B")
    assert term_gpas([unknown, known]) == {"2025 Spring Semester": 3.0}


def test_retaken_course_does_not_move_its_term() -> None:
    """A course in two record grids does not vote on either grid's term."""
    spring = "2025 Spring Semester (01/13/2025-05/03/2025)"
    fall = "2024 Fall Semester (08/24/2024-12/14/2024)"
    raw = {
        "record": [
            {"rows": [graded("MATH 1550 - Calculus I", "F", "5", "0.0"),
                      graded("ENGL 1001 - Composition", "A", "3", "12.0")]},
            {"rows": [graded("MATH 1550 - Calculus I", "B", "5", "15.0"),
                      graded("CSC 1350 - Computer Science I", "A", "4", "16.0")]},
        ],
        "progress": [{"rows": [
            {"Registrations Used": "ENGL 1001 - Composition", "Academic Period": fall},
            {"Registrations Used": "MATH 1550 - Calculus I", "Academic Period": spring},
            {"Registrations Used": "CSC 1350 - Computer Science I", "Academic Period": spring},
        ]}],
    }
    data = parse_workday(raw, FALL_DAY)
    assert [(c.course_code, c.grade, c.term) for c in data.courses] == [
        ("MATH 1550", "F", "2024 Fall Semester"),
        ("ENGL 1001", "A", "2024 Fall Semester"),
        ("MATH 1550", "B", "2025 Spring Semester"),
        ("CSC 1350", "A", "2025 Spring Semester"),
    ]


def test_pass_and_withdraw_hours_leave_gpa_alone() -> None:
    """Only letter grades on the GPA scale count toward GPA hours."""
    raw = fall_record(
        graded("CSC 1350 - Computer Science I", "A", "3", "12.0"),
        graded("KIN 1001 - Fitness", "P", "3", "0.0"),
        graded("PHIL 1000 - Philosophy", "W", "3", "0.0"),
    )
    data = parse_workday(raw, FALL_DAY)
    assert (data.gpa, data.completed_credit_hours) == (4.0, 3)


def test_fractional_credit_gpa_stays_on_scale() -> None:
    """GPA divides by the real credit hours, not rounded ones."""
    raw = fall_record(graded("MUS 1001 - Ensemble", "A", "1.4", "5.6"))
    data = parse_workday(raw, FALL_DAY)
    assert data.gpa == 4.0
    assert data.completed_credit_hours == 1
