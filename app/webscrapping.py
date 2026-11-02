#this is where the contents of the web scrapping will be for when we get course catalogs
# usage: python webscrapping.py [URL ...] [--out FILE] [--debug]
# it works on any lsu.edu degree page that lists courses in tables with a credits column
import argparse
import requests
import json
import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from tiger_catalog import DATA_FILE

DEFAULT_URL = "https://www.lsu.edu/eng/cse/programs/undergraduate_program/undergraduate_major.php"
DEBUG = False
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
# page chrome that never holds degree requirements
SKIP_TAGS = ["header", "footer", "nav", "script", "style", "noscript"]
POPUP_SELECTOR = "[class*=cookie i], [id*=cookie i], [class*=modal i], [id*=modal i]"
NOTE_TAGS = ["p", "li"]

COURSE_CODE = re.compile(r"[A-Z]{2,5}\s+\d{4}")
CODE_ANYWHERE = re.compile(r"\b[A-Z]{2,5}\s+\d{4}\b")
# matches "3", "3-4", "3 - 4", "3 or 5" and "3 to 6"
CREDITS = re.compile(r"(\d+)(?:\s*(?:-|–|or|to)\s*(\d+))?")
CREDIT_HOURS_TEXT = re.compile(r"(\d+)\s+credit\s+hours", re.IGNORECASE)


def log(*args) -> None:
    if DEBUG:
        print(*args)


def clean_text(element: Tag) -> str:
    # removes zero width spaces and collapses repeated whitespace
    return " ".join(element.get_text(" ", strip=True).replace("​", "").split())


def snake_case(title: str) -> str:
    # "Approved Electives" -> "approved_electives"
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def fetch_page(url: str) -> BeautifulSoup:
    print("we are fetching your webpage...", url)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    print("Status:", response.status_code, "Characters:", len(response.text))

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(SKIP_TAGS):
        tag.decompose()
    # cookie banners and video popups sit at the bottom of every lsu.edu page
    for tag in soup.select(POPUP_SELECTOR):
        tag.decompose()
    return soup


def find_columns(table: Tag) -> tuple[int, int, int | None]:
    # reads the header row to find which column holds the code, the name and the credits
    # pages differ: some use "Course Number | Course Description | Credit Hours",
    # others add a prerequisites column or call the credits column "Hours"
    first_row = table.find("tr")
    headers = [clean_text(cell).lower() for cell in first_row.find_all(["td", "th"])] if first_row else []

    def find(pattern: str) -> int | None:
        for index, header in enumerate(headers):
            if re.search(pattern, header):
                return index
        return None

    code = find(r"number|code")
    if code is None:
        code = find(r"^course$")
    if code is None:
        code = 0
    name = find(r"description|title|name")
    if name is None:
        name = code + 1
    credits = find(r"credit|hour|hrs")
    return code, name, credits


def parse_credits(text: str) -> tuple[int, int] | None:
    # returns (min, max) credits, or None when the cell is not a credit amount
    match = CREDITS.fullmatch(text.strip())
    if match is None:
        return None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else low
    return low, high


def extract_table_data(table: Tag, category: str, url: str) -> tuple[list[dict], list[dict]]:
    courses: list[dict] = []
    requirements: list[dict] = []
    code_col, name_col, credits_col = find_columns(table)

    for row in table.select("tr"):
        cells = [clean_text(cell) for cell in row.find_all(["td", "th"])]
        # tables without a credits column (like prerequisite lists) are not degree requirements
        column = credits_col if credits_col is not None else len(cells) - 1
        if len(cells) <= max(code_col, name_col, column):
            continue

        code, name = cells[code_col], cells[name_col]
        credits = parse_credits(cells[column])
        if credits is None:
            log("Skipping the invalid contents:", code)
            continue
        low, high = credits

        if COURSE_CODE.fullmatch(code):
            course = {
                "id": code.lower().replace(" ", "-"),
                "course_code": code,
                "course_name": name,
                "credits": low,
                "category": category,
                "source_url": url
            }
            if high != low:
                course["credits_max"] = high
            courses.append(course)
            log("Extracted:", course)
        else:
            # rows like "MATH 1022 or MATH 1023" or "Technical Elective" list options instead of one course
            requirement = {
                "listed_options": code,
                "description": name,
                "credits": low,
                "category": category,
            }
            if high != low:
                requirement["credits_max"] = high
            requirements.append(requirement)
            log("Special requirement extracted:", code)
    return courses, requirements


def is_note(element: Tag) -> bool:
    if element.find_parent(NOTE_TAGS + ["table"]):
        return False
    if element.name in NOTE_TAGS:
        return True
    # some pages put text straight into a div (like accordion panels) instead of a <p>
    if element.name == "div" and not element.find(NOTE_TAGS + HEADING_TAGS + ["div", "table"]):
        return any(text.strip() for text in element.find_all(string=True, recursive=False))
    return False


def split_sections(soup: BeautifulSoup) -> list[dict]:
    # breaks the page into one section per heading with the tables and text under it
    sections: list[dict] = []
    for heading in soup.find_all(HEADING_TAGS):
        title = clean_text(heading)
        if not title:
            continue
        tables: list[Tag] = []
        notes: list[str] = []
        for element in heading.next_elements:
            if not isinstance(element, Tag):
                continue
            if element.name in HEADING_TAGS:
                break
            if element.name == "table":
                tables.append(element)
            # whole paragraphs and list items, so links inside a sentence don't split it up
            elif is_note(element):
                text = clean_text(element)
                if text:
                    notes.append(text)
        sections.append({"title": title, "level": heading.name, "tables": tables, "notes": notes})
    return sections


def looks_like_requirement(notes: list[str]) -> bool:
    # a section without tables is only kept when its text talks about courses or credit hours
    text = " ".join(notes)
    return bool(CODE_ANYWHERE.search(text) or CREDIT_HOURS_TEXT.search(text))


def extract_requirements(soup: BeautifulSoup, url: str) -> dict:
    sections = split_sections(soup)
    program = next((s["title"] for s in sections if s["level"] == "h1"), "")
    sections = [s for s in sections if s["level"] != "h1"]

    # Heading levels on lsu.edu pages are not reliable (a concentration can be an h3
    # while its "Required Courses" subsection is an h2). What is reliable is that
    # subsection titles repeat under every concentration or track while most other headings are unique.
    title_counts = Counter(s["title"] for s in sections)

    categories: dict[str, dict] = {}
    concentrations: dict[str, dict] = {}
    current: dict | None = None
    current_name = ""
    seen_table = False

    for index, section in enumerate(sections):
        title = section["title"]
        repeated = title_counts[title] > 1
        next_repeated = index + 1 < len(sections) and title_counts[sections[index + 1]["title"]] > 1

        if not repeated and not section["tables"] and next_repeated:
            # a unique heading with no table of its own, followed by repeated subsections,
            # is a concentration or track (e.g. "Cybersecurity" or "Petroleum Engineering (CCUS)")
            current, current_name = {}, title
            concentrations[title] = current
            continue

        if current is not None and (repeated or section["tables"]):
            # inside a concentration, any section with courses belongs to it until the next one starts
            key = snake_case(title)
            if key in ("other_requirements", "notes"):
                # a subsection called "Other Requirements" must not mix with the special rows list
                key += "_courses"
            current.setdefault(key, [])
            current.setdefault("other_requirements", [])
            current.setdefault("notes", [])
            for table in section["tables"]:
                courses, requirements = extract_table_data(table, f"{current_name} - {title}", url)
                current[key].extend(courses)
                current["other_requirements"].extend(requirements)
            current["notes"].extend(section["notes"])
            seen_table = seen_table or bool(section["tables"])
            continue

        current = None
        if not section["tables"]:
            # text only sections before the first table are page intro, not requirements
            if seen_table and looks_like_requirement(section["notes"]):
                categories[title] = {"courses": [], "requirements": [], "notes": section["notes"]}
            continue

        seen_table = True
        entry = categories.setdefault(title, {"courses": [], "requirements": [], "notes": []})
        for table in section["tables"]:
            courses, requirements = extract_table_data(table, title, url)
            entry["courses"].extend(courses)
            entry["requirements"].extend(requirements)
        entry["notes"].extend(section["notes"])

    for name, details in concentrations.items():
        details.setdefault("other_requirements", [])
        details.setdefault("notes", [])
        # concentrations without course tables usually state a credit hour total in their text
        has_courses = any(value for key, value in details.items() if key not in ("notes", "other_requirements"))
        hours = CREDIT_HOURS_TEXT.search(" ".join(details["notes"]))
        if not has_courses and hours:
            details["required_credit_hours"] = int(hours.group(1))
        print("Concentration:", name, {key: len(value) for key, value in details.items() if isinstance(value, list)})

    for name, entry in categories.items():
        print("Category:", name, "courses:", len(entry["courses"]), "special rows:", len(entry["requirements"]))

    total = sum(len(entry["courses"]) for entry in categories.values())
    total += sum(len(value) for details in concentrations.values() for key, value in details.items() if key != "notes" and isinstance(value, list))
    if total == 0:
        raise ValueError("No course tables with a credits column were found on this page")

    return {"program": program, "categories": categories, "concentrations": concentrations}


def default_output(url: str) -> Path:
    # the default page feeds the app's catalog, other majors get their own file
    if url == DEFAULT_URL:
        return DATA_FILE
    # PurePosixPath because URL paths use "/" even on Windows
    parts = [part for part in PurePosixPath(urlparse(url).path).with_suffix("").parts if part not in ("/", "index")]
    return DATA_FILE.parent / "majors" / f"{'-'.join(parts)}.json"


def save_json(url: str, data: dict, output: Path) -> None:
    dataset = {
        "source_url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    output.parent.mkdir(parents = True, exist_ok = True)
    with output.open("w", encoding = "utf-8") as file:
        json.dump(dataset, file, indent = 4, ensure_ascii = False)
    print("Saved JSON to:", output)


def main() -> None:
    global DEBUG
    parser = argparse.ArgumentParser(description="Scrape degree requirements from lsu.edu major pages.")
    parser.add_argument("urls", nargs="*", default=[DEFAULT_URL], help="degree pages to scrape")
    parser.add_argument("--out", type=Path, help="output file (only when scraping one URL)")
    parser.add_argument("--debug", action="store_true", help="print every row that is extracted")
    args = parser.parse_args()
    DEBUG = args.debug
    if args.out and len(args.urls) > 1:
        parser.error("--out can only be used with a single URL")

    for url in args.urls:
        try:
            data = extract_requirements(fetch_page(url), url)
            save_json(url, data, args.out or default_output(url))
            print("Your scraping has been completed\n")

        except requests.RequestException as error:
            print("webiste request has failed:", error)

        except ValueError as error:
            print("There was an extraction error:", error)


if __name__ == "__main__":
    main()
