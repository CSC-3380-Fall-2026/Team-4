"""Read an LSU unofficial transcript PDF into draft profile fields."""

import re
from io import BytesIO

from pydantic import BaseModel, Field
from pypdf import PdfReader

from models.tiger_profile import ProfileCourse

MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
MAX_PAGES: int = 20

# A course row's description may wrap onto one extra line (for example a
# "Communication Intensive" tag), but never further, so a match can never
# stretch across an unrelated row.
LINE: str = r"[^\n]{1,120}?"
# A course's grade sometimes sits on its own line below the title, rather
# than right after it, so the gap before it may include one line break.
GAP: str = r"(?:[ \t]+|[ \t]*\n[ \t]*)"
COURSE_PATTERN: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9])(?P<dept>[A-Z]{2,6})[ \t]?(?P<num>\d{3,4})[ \t]+"
    rf"(?P<body>{LINE}(?:\n{LINE}){{0,1}}?){GAP}"
    rf"(?P<grade>[A-F][+-]?|IP)(?:[ \t]*\(HNR\))?{GAP}"
    rf"(?P<carried>\d+\.\d{{2}}){GAP}"
    r"(?P<earned>\d+\.\d{2})"
)
CUMULATIVE_PATTERN: re.Pattern[str] = re.compile(
    r"Cumulative \(Institutional\)[ \t]+(?P<carried>\d+\.\d{2})"
    r"[ \t]+(?P<earned>\d+\.\d{2})[ \t]+(?P<gpa>\d+\.\d{3})"
)
SKIP_PREFIXES: tuple[str, ...] = ("communication intensive",)


class ParsedTranscript(BaseModel):
    """Draft profile fields read from an unofficial transcript."""

    gpa: float | None = Field(default=None, ge=0, le=4.3)
    completed_credit_hours: int = Field(default=0, ge=0)
    courses: list[ProfileCourse] = Field(default_factory=list)


def read_pages(data: bytes) -> str:
    """Open a PDF and join the text of its pages.

    Args:
        data: Raw bytes of the uploaded file.

    Returns:
        The text of every page.

    Raises:
        ValueError: For a protected, empty, or overly long PDF.
        Exception: Any pypdf error on a damaged file; the caller converts it.
    """
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("That PDF is password protected.")
    pages = reader.pages
    if len(pages) == 0:
        raise ValueError("That PDF has no pages.")
    if len(pages) > MAX_PAGES:
        raise ValueError("That PDF has too many pages to be a transcript.")
    return "\n".join(page.extract_text() or "" for page in pages)


def extract_text(data: bytes) -> str:
    """Read the text content of an uploaded PDF.

    Args:
        data: Raw bytes of the uploaded file.

    Returns:
        The PDF's text, page by page.

    Raises:
        ValueError: If the file is too large, or not a readable, unprotected
            PDF with text.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("That PDF is too large (5 MB limit).")
    try:
        text = read_pages(data)
    except ValueError:
        raise
    except Exception as error:
        # pypdf raises many error types on damaged files; all mean the same
        # thing to the student.
        raise ValueError("That file is not a readable PDF.") from error
    if not text.strip():
        raise ValueError(
            "No text could be read from that PDF. Export it directly from "
            "Workday rather than scanning a printed copy."
        )
    return text


def clean_title(body: str) -> str:
    """Turn a matched course body into a single readable course title.

    Args:
        body: Raw text between a course's number and its grade.

    Returns:
        The title with wrapped description lines removed.
    """
    kept = [
        line.strip().lstrip("-").strip()
        for line in body.splitlines()
        if not line.strip().lower().startswith(SKIP_PREFIXES)
    ]
    return " ".join(" ".join(kept).split())


def read_courses(text: str) -> list[ProfileCourse]:
    """Pull completed, grade-earning courses out of transcript text.

    Only real letter grades count, and only when credit was earned, so
    in-progress courses, failed courses, and pass/fail transfer or exam
    credit are left out. A course taken more than once keeps its most
    recent earned attempt.

    Args:
        text: Full transcript text.

    Returns:
        Completed courses in first-seen order.
    """
    courses: dict[str, ProfileCourse] = {}
    for match in COURSE_PATTERN.finditer(text):
        earned = float(match["earned"])
        if match["grade"] == "IP" or earned <= 0:
            continue
        code = f"{match['dept']} {match['num']}"
        courses[code] = ProfileCourse(
            course_code=code,
            course_name=clean_title(match["body"])[:100] or code,
            credits=round(earned),
        )
    return list(courses.values())


def read_summary(text: str) -> tuple[float | None, int]:
    """Read the most recent cumulative institutional GPA and credit hours.

    The last "Cumulative (Institutional)" line in the transcript always
    carries the latest totals forward, even during an in-progress term.

    Hours come from the "Carried" column: GPA hours, which include courses
    graded F, unlike "Earned".

    Args:
        text: Full transcript text.

    Returns:
        The cumulative GPA and GPA (carried) credit hours, or (None, 0) if
        the transcript has no cumulative summary line.
    """
    matches = list(CUMULATIVE_PATTERN.finditer(text))
    if not matches:
        return None, 0
    last = matches[-1]
    return float(last["gpa"]), round(float(last["carried"]))


def read_transcript(text: str) -> ParsedTranscript:
    """Build draft profile fields from transcript text.

    Args:
        text: Full transcript text.

    Returns:
        The parsed GPA, credit hours, and completed courses.

    Raises:
        ValueError: If the text has no recognizable transcript content.
    """
    gpa, hours = read_summary(text)
    courses = read_courses(text)
    if gpa is None and not courses:
        raise ValueError(
            "That didn't look like an LSU unofficial transcript. You can "
            "enter your information in the form below instead."
        )
    return ParsedTranscript(
        gpa=gpa, completed_credit_hours=hours, courses=courses
    )


def parse_upload(data: bytes) -> ParsedTranscript:
    """Read an uploaded transcript PDF into draft profile fields.

    Args:
        data: Raw bytes of the uploaded file.

    Returns:
        The parsed GPA, credit hours, and completed courses.

    Raises:
        ValueError: If the file cannot be read as a transcript.
    """
    return read_transcript(extract_text(data))
