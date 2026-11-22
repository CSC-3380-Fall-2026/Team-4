"""Check transcript parsing and the profile upload route that uses it."""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vercel_entry import app
import tiger_transcript
from fake_supabase import FakeDatabase

# A synthetic transcript with the same structure as a real LSU unofficial
# transcript: a "Credit by Exam" table with entries wrapped across several
# lines, a completed semester with a wrapped course description and an
# honors grade suffix, a retaken course, a failed course, and a trailing
# in-progress semester. None of this is a real student's data.
SAMPLE: str = """
Credit by Exam
Credit Source/Type Course Grade Hours Carried Hours Earned Repeat
Assessment and Learning in Knowledge Spaces MATH 1021 - College Algebra Pass 0.00 3.00 Y
AP - Advanced Placement Exam: United States
History: 4
HIST 2057 - The United States from 1865 to the
Present
Pass 0.00 3.00 Y

Fall Semester 2024
Academic Standing Good Standing
ENGL 1001 ENGL COMPOSITION A 3.00 3.00
CSC 1350 Computer Science I for Majors
Communication Intensive : Written and Technological
A- 3.00 3.00
MATH 1550 HON- CALCULUS I B+ (HNR) 5.00 5.00
PHYS 2110 Introductory Physics F 3.00 0.00
   Carried  Earned  GPA
Academic Period 11.00 11.00 3.400
Cumulative (Institutional) 11.00 11.00 3.400
Cumulative including Transfer Credit 11.00 22.00 3.400

Spring Semester 2025
PHYS 2110 Introductory Physics B 3.00 3.00
CSC 1351 Computer Science II for Majors A 3.00 3.00
MATH 1552 Calculus II A- 4.00 4.00
   Carried  Earned  GPA
Academic Period 10.00 10.00 3.300
Cumulative (Institutional) 21.00 21.00 3.340
Cumulative including Transfer Credit 21.00 32.00 3.340

Fall Semester 2025
CSC 2259 Discrete Structures IP 0.00 0.00
CSC 3380 Object Oriented Design IP 0.00 0.00
   Carried  Earned  GPA
Academic Period 0.00 0.00 0.000
Cumulative (Institutional) 21.00 21.00 3.340
Cumulative including Transfer Credit 21.00 32.00 3.340

End of Unofficial Transcript
"""


def browser(token: str = "") -> TestClient:
    """Create a separate browser, optionally signed in.

    Args:
        token: Access token for the login cookie, or empty for signed out.

    Returns:
        A test browser with its own cookie jar.
    """
    tab: TestClient = TestClient(app)
    if token:
        tab.cookies.set("tiger_access", token)
    return tab


def test_reads_summary_and_courses() -> None:
    """Read the latest cumulative GPA, hours, and completed courses."""
    parsed = tiger_transcript.read_transcript(SAMPLE)
    assert parsed.gpa == 3.34
    assert parsed.completed_credit_hours == 21
    codes = [course.course_code for course in parsed.courses]
    assert codes == [
        "ENGL 1001",
        "CSC 1350",
        "MATH 1550",
        "PHYS 2110",
        "CSC 1351",
        "MATH 1552",
    ]


def test_skips_credit_by_exam() -> None:
    """Never include pass/fail transfer or AP exam credit as a course."""
    parsed = tiger_transcript.read_transcript(SAMPLE)
    codes = {course.course_code for course in parsed.courses}
    assert "MATH 1021" not in codes
    assert "HIST 2057" not in codes


def test_skips_in_progress_courses() -> None:
    """Never include a course that has not been completed yet."""
    parsed = tiger_transcript.read_transcript(SAMPLE)
    codes = {course.course_code for course in parsed.courses}
    assert "CSC 2259" not in codes
    assert "CSC 3380" not in codes


def test_retake_keeps_latest_attempt() -> None:
    """Keep the passing retake, not the earlier failed attempt."""
    parsed = tiger_transcript.read_transcript(SAMPLE)
    retake = next(
        course for course in parsed.courses if course.course_code == "PHYS 2110"
    )
    assert retake.credits == 3
    assert retake.course_name == "Introductory Physics"


def test_cleans_wrapped_and_honors_titles() -> None:
    """Drop a wrapped description line and an honors grade suffix."""
    parsed = tiger_transcript.read_transcript(SAMPLE)
    by_code = {course.course_code: course for course in parsed.courses}
    assert by_code["CSC 1350"].course_name == "Computer Science I for Majors"
    assert by_code["MATH 1550"].credits == 5


def test_unrecognized_text_is_rejected() -> None:
    """Refuse text with no transcript content instead of saving zeros."""
    with pytest.raises(ValueError):
        tiger_transcript.read_transcript("Not a transcript at all.")


def test_extract_text_rejects_bad_file() -> None:
    """Reject bytes that are not a readable PDF."""
    with pytest.raises(ValueError):
        tiger_transcript.extract_text(b"not a pdf")


def test_upload_signed_out_redirects(fake_db: FakeDatabase) -> None:
    """Send a signed-out upload to the login page.

    Args:
        fake_db: Fake Supabase.
    """
    tab: TestClient = browser()
    tab.cookies.set("tiger_csrf", "abc")
    response: httpx.Response = tab.post(
        "/profile/transcript",
        data={"csrf_token": "abc"},
        files={"transcript": ("transcript.pdf", b"x", "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_upload_prefills_for_review(
    fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Show parsed values for review without saving them.

    Args:
        fake_db: Fake Supabase.
        monkeypatch: Fixture replacing the transcript parser.
    """
    monkeypatch.setattr(
        tiger_transcript, "parse_upload", lambda data: tiger_transcript.read_transcript(SAMPLE)
    )
    tab: TestClient = browser("token-reviewer")
    tab.get("/profile")
    token: str = tab.cookies.get("tiger_csrf")
    response: httpx.Response = tab.post(
        "/profile/transcript",
        data={"csrf_token": token},
        files={"transcript": ("transcript.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 200
    assert "Nothing is saved yet" in response.text
    assert "3.34" in response.text
    assert "Computer Science I for Majors" in response.text
    assert fake_db.rows("profiles") == []


def test_upload_rejects_unparseable_file(
    fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Show a clear error instead of saving anything when parsing fails.

    Args:
        fake_db: Fake Supabase.
        monkeypatch: Fixture replacing the transcript parser.
    """
    def fail(data: bytes) -> tiger_transcript.ParsedTranscript:
        raise ValueError("That didn't look like a transcript.")

    monkeypatch.setattr(tiger_transcript, "parse_upload", fail)
    tab: TestClient = browser("token-reviewer")
    tab.get("/profile")
    token: str = tab.cookies.get("tiger_csrf")
    response: httpx.Response = tab.post(
        "/profile/transcript",
        data={"csrf_token": token},
        files={"transcript": ("transcript.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 400
    assert "didn" in response.text


def test_upload_rejects_expired_form(fake_db: FakeDatabase) -> None:
    """Reject an upload whose form token does not match the cookie.

    Args:
        fake_db: Fake Supabase.
    """
    tab: TestClient = browser("token-reviewer")
    tab.get("/profile")
    response: httpx.Response = tab.post(
        "/profile/transcript",
        data={"csrf_token": "wrong"},
        files={"transcript": ("transcript.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 403


def test_upload_requires_a_file(fake_db: FakeDatabase) -> None:
    """Reject a submission with no file attached.

    Args:
        fake_db: Fake Supabase.
    """
    tab: TestClient = browser("token-reviewer")
    tab.get("/profile")
    token: str = tab.cookies.get("tiger_csrf")
    response: httpx.Response = tab.post(
        "/profile/transcript", data={"csrf_token": token}
    )
    assert response.status_code == 400
    assert "Choose a transcript" in response.text


def test_reviewed_draft_can_then_be_saved(
    fake_db: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save the parsed values only after the student submits the real form.

    Args:
        fake_db: Fake Supabase.
        monkeypatch: Fixture replacing the transcript parser.
    """
    monkeypatch.setattr(
        tiger_transcript, "parse_upload", lambda data: tiger_transcript.read_transcript(SAMPLE)
    )
    tab: TestClient = browser("token-reviewer")
    tab.get("/profile")
    token: str = tab.cookies.get("tiger_csrf")
    tab.post(
        "/profile/transcript",
        data={"csrf_token": token},
        files={"transcript": ("transcript.pdf", b"x", "application/pdf")},
    )
    courses_text: str = "\n".join(
        f"{course.course_code}, {course.credits}, {course.course_name}"
        for course in tiger_transcript.read_transcript(SAMPLE).courses
    )
    response: httpx.Response = tab.post(
        "/profile",
        data={
            "csrf_token": token,
            "username": "reviewer",
            "gpa": "3.34",
            "hours": "21",
            "courses": courses_text,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    saved = fake_db.rows("profiles")[0]
    assert saved["completed_credit_hours"] == 21
    assert len(saved["courses"]) == 6
