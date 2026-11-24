"""Read profile fields from the profile form and from an LSU unofficial transcript PDF."""

import re
from io import BytesIO

from pypdf import PdfReader

from models.tiger_profiles import ParsedTranscript, ProfileCourse, ProfileRecord

# Vercel refuses request bodies over 4.5 MB, so stay below it.
MAX_UPLOAD_BYTES: int = 4 * 1024 * 1024
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


def whole_number(text: str) -> bool:
    """Tell whether text is a plain ASCII whole number.

    str.isdigit() alone also accepts characters such as "²" that int()
    cannot read.

    Args:
        text: Text to check.

    Returns:
        True for text made only of the digits 0-9.
    """
    return text.isascii() and text.isdigit()


def parse_courses(text: str) -> list[ProfileCourse]:
    """Turn lines like "CSC 1350, 4, Computer Science I" into course records.

    Args:
        text: One completed course per line as code, credits, then name.

    Returns:
        Course records ready to store with the profile.

    Raises:
        ValueError: If a line is incomplete or its credits are invalid.
    """
    courses: list[ProfileCourse] = []
    for line in text.splitlines():
        if line.strip():
            courses.append(parse_line(line))
    return courses


def parse_line(line: str) -> ProfileCourse:
    """Read one completed-course line.

    Args:
        line: Text formatted as code, credits, name.

    Returns:
        One course record.

    Raises:
        ValueError: If the line is incomplete or its credits are invalid.
    """
    parts: list[str] = [part.strip() for part in line.split(",", 2)]
    if len(parts) < 3 or not parts[0] or not parts[2]:
        raise ValueError(f"Use code, credits, name on each line: {line.strip()}")
    if not whole_number(parts[1]) or int(parts[1]) > 12:
        raise ValueError(f"Credits must be a whole number: {line.strip()}")
    return ProfileCourse(
        course_code=parts[0][:20],
        course_name=parts[2][:100],
        credits=int(parts[1]),
    )


def parse_gpa(text: str) -> float | None:
    """Read an optional GPA between 0.0 and 4.3.

    Args:
        text: Raw GPA text from the form.

    Returns:
        The GPA, or None when left blank.

    Raises:
        ValueError: If the text is not a valid GPA.
    """
    if not text.strip():
        return None
    value: float = float(text)
    if not 0 <= value <= 4.3:
        raise ValueError("GPA must be between 0.0 and 4.3.")
    return round(value, 2)


def parse_hours(text: str) -> int:
    """Read completed GPA credit hours.

    Args:
        text: Raw credit-hour text from the form.

    Returns:
        A whole number of hours, or 0 when left blank.

    Raises:
        ValueError: If the text is not a non-negative whole number.
    """
    value = text.strip()
    if not value:
        return 0
    if not whole_number(value) or int(value) > 400:
        raise ValueError("Completed credit hours must be a whole number.")
    return int(value)


def read_form(data: dict[str, str]) -> ProfileRecord:
    """Validate every profile field submitted by the form.

    Args:
        data: Submitted form values.

    Returns:
        The validated profile.

    Raises:
        ValueError: With a message for the first invalid field.
    """
    username: str = data.get("username", "").strip()
    if len(username) > 40:
        raise ValueError("Username must be 40 characters or fewer.")
    return ProfileRecord(
        username=username or None,
        gpa=parse_gpa(data.get("gpa", "")),
        completed_credit_hours=parse_hours(data.get("hours", "")),
        courses=parse_courses(data.get("courses", "")),
    )


def friendly(error: ValueError) -> str:
    """Turn a form validation error into a message for the student.

    Args:
        error: The validation error.

    Returns:
        A readable message; Python's own float errors are replaced.
    """
    text = str(error)
    if text.startswith("could not convert"):
        return "GPA must be a number between 0.0 and 4.3."
    return text


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
        raise ValueError("That PDF is too large (4 MB limit).")
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
