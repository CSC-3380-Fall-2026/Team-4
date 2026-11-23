#this is where the contents of the web scrapping will be for when we get course catalogs
import requests
import json
import re


from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString 
from pathlib import Path
from models.tiger_catalog import ConcentrationRequirements, ScrapedCourse 

URL = "https://www.lsu.edu/eng/cse/programs/undergraduate_program/undergraduate_major.php"

DEBUG = False

CATEGORIES = [ "Core Coursework", "Technical Requirements", "Math Requirements", "Other Requirements"]
STOP_HEADINGS = set(CATEGORIES + ["Concentrations"])


def fetch_page(url: str) -> str:
    '''Here is where we fetched the HTML content from the specified webpage.'''
    print("we are fetching your webpage...")
    response = requests.get(url, timeout=15)

    response.raise_for_status()

    print("Status:", response.status_code)
    print("Characters:", len(response.text))
    return response.text 

def inspect_html(html: str) -> BeautifulSoup:
    """This is where I parsed the webpage HTML and inspected the table structure."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr")
    print("\n Total table rows:", len(rows))

    if DEBUG:
        print("\n First 5 rows:")
        for row in rows[:5]:
            print(row.get_text(" ",strip=True))
    return soup

def find_categories(soup: BeautifulSoup) -> dict[str, Tag]:
    """This is where I located the degree requirement categories in the webpage HTML."""

    found: dict[str, Tag] = {}
    headings = soup.find_all(["h2", "h3", "h4"])

    for heading in headings:
        title = heading.get_text(" ", strip=True)
        if title in CATEGORIES:
            found[title] = heading
            if DEBUG:
                print("Found category:", title)

    missing = set(CATEGORIES) - set(found)

    if missing:
        raise ValueError(f"Missing category headings: {sorted(missing)}")

    return found 

def section_content(heading: Tag) -> tuple[list[Tag], list[str]]:
    """I extracted the tables and text notes from a degree requirement section."""

    tables: list[Tag] = []
    notes: list[str] = []
    for element in heading.next_elements:
        if isinstance(element, Tag):
            if element.name in["h2", "h3", "h4"]:
                title = element.get_text(" ", strip=True)
                if title in STOP_HEADINGS:
                    break
            if element.name == "table":
                tables.append(element)
        elif isinstance(element, NavigableString):
                    parent = element.parent

                    if parent is None:
                        continue

                    if element.find_parent(["h2","h3","h4"]):
                        continue 

                    if element.find_parent(["Script", "style"]):
                        continue 

                    text = str(element).strip()
                    if text:
                        notes.append(text)
    return tables, notes

def table_data(table: Tag, category: str) -> tuple[list[dict], list[dict]]:
    """I extracted course information and additonal requirements from an HTML table."""

    courses: list[dict] = []
    requirements: list[dict] = []
    rows = table.select("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        code = cells[0].get_text(" ", strip=True)
        name = cells[1].get_text(" ", strip=True)
        credits = cells[2].get_text(" ", strip=True)
        if not credits.isdigit():
            if DEBUG:
                print("Skipping the invalid contents:", code)
            continue
        valid_code = re.fullmatch(r"[A-Z]{2,5}\s+\d{4}", code)

        if valid_code:
            course = {
            "id": code.lower().replace(" ", "-"),
            "course_code": code,
            "course_name": name,
            "credits": int(credits),
            "category": category,
            "source_url": URL
        }

            ScrapedCourse(**course)
            courses.append(course)
            if DEBUG:
                print("Extracted:", course)
        else:
                requirement = {
                "listed_options": code,
                "description": name,
                "credits": int(credits),
                "category": category,
        }
                requirements.append(requirement)
                if DEBUG:
                    print("Special requirement extracted:", code)
    return courses, requirements

def all_courses(soup: BeautifulSoup) -> dict:
    """I extracted and organized all the general degree course requirements for our webscrapper."""

    headings = find_categories(soup)
    result: dict = {}
    for category in CATEGORIES:
        print("\nProcessing:", category)
        heading = headings[category]
        tables, notes = section_content(heading)
        courses: list[dict] = []
        requirements: list[dict] = []
        print("Tables have been found:", len(tables))

        for table in tables:
            found_courses, found_requiremnts = (table_data(table, category))
            courses.extend(found_courses)
            requirements.extend(found_requiremnts)

        if category != "Technical Requirements":
            if not tables:
                raise ValueError(f"No tables found for {category}")
            if not courses and not requirements:
                raise ValueError(f"No rows were extracted for {category}")
        else:
            if not notes:
                raise ValueError("No technical requirement text found")

        result[category] = {
            "courses": courses,
            "requirements": requirements,
            "notes": notes
        }
        print("Courses:", len(courses))
        print("Special rows:", len(requirements))
        print("Text fragments:", len(notes))
    return result 

def concentration_headings(soup: BeautifulSoup) -> list[Tag]:
    """I located concentation headings from the webpage HTML."""

    headings: list[Tag] = []

    section = soup.find("h2", string=lambda text: (text is not None and text.strip() == "Concentrations"))

    if not isinstance(section, Tag):
        raise ValueError("Concentration section has not been found")

    for heading in section.find_all_next(["h2", "h3"]):
        title = heading.get_text(" ", strip=True)

        if heading.name == "h2":
            if title not in ("Required Courses", "Approved Electives"):
                break

        if heading.name == "h3":
            headings.append(heading)
    if not headings:
        raise ValueError("No concentrations headings were found")

    return headings

SECTION_KEYS = {"Required Courses": "required_courses", "Approved Electives": "approved_electives"}


def is_boundary(element: Tag, heading: Tag) -> bool:
    """Check whether an element ends the current concentration section.

    Args:
        element: Tag being visited.
        heading: Heading that started the section.

    Returns:
        True if scanning should stop at this element.
    """
    if element.name == "h3" and element is not heading:
        return True
    if element.name == "footer":
        return True
    return element.name in ("a", "button") and element.get_text(" ", strip=True) == "Top"


def add_element(element: Tag, name: str, section: str | None, details: dict) -> str | None:
    """Fold one element into a concentration's details.

    Args:
        element: Tag being visited.
        name: Concentration name.
        section: Current section key, if any.
        details: Details dict updated in place.

    Returns:
        The (possibly updated) current section key.
    """
    if element.name in ("h2", "h3", "h4"):
        return SECTION_KEYS.get(element.get_text(" ", strip=True))
    if element.name == "table" and section is not None:
        courses, requirements = table_data(element, f"{name} - {section.replace('_', ' ')}")
        details[section].extend(courses)
        details["other_requirements"].extend(requirements)
    elif element.name == "p" and element.find_parent("table") is None:
        note = element.get_text(" ", strip=True)
        if note:
            details["notes"].append(note)
    return section


def scan_section(heading: Tag, name: str) -> dict:
    """Collect course lists and notes beneath a concentration heading.

    Args:
        heading: Concentration heading tag.
        name: Concentration name.

    Returns:
        Details dict for the concentration.
    """
    details: dict = {"required_courses": [], "approved_electives": [], "other_requirements": [], "notes": []}
    section: str | None = None

    for element in heading.next_elements:
        if not isinstance(element, Tag):
            continue
        if is_boundary(element, heading):
            break
        section = add_element(element, name, section, details)
    return details


def credit_fallback(soup: BeautifulSoup, name: str, details: dict) -> None:
    """Record a total credit requirement for concentrations lacking course tables.

    Args:
        soup: Parsed page.
        name: Concentration name.
        details: Details dict updated in place.
    """
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    section_name = " ".join(name.split())
    before, separator, section_text = page_text.rpartition(section_name)

    if not separator:
        raise ValueError(f"Section text not found for {name}")

    match = re.search(r"Students\s+must\s+complete\s+a\s+total\s+of\s+"r"(\d+)\s+credit\s+hours\b[^.]*\.",section_text,re.IGNORECASE)

    if not match:
        raise ValueError(f"Credit requirement not found for {name}")

    details["required_credit_hours"] = int(match.group(1))
    details["notes"].append(match.group(0))


def check_details(name: str, details: dict) -> None:
    """Validate a concentration's details.

    Args:
        name: Concentration name.
        details: Details dict to check.
    """
    if "required_credit_hours" in details:
        if details["required_credit_hours"] <= 0:
            raise ValueError(f"Invalid credit requirement for {name}")
    elif not details["required_courses"] or not details["approved_electives"]:
        raise ValueError(f"Incomplete course lists for {name}")


def extract_concentrations(soup: BeautifulSoup) -> dict[str, dict]:
    """Extracted required courses, electives, and credit requirements for all the concentrations.

    Args:
        soup: Parsed page.

    Returns:
        Mapping of concentration name to its details.
    """

    results: dict[str, dict] = {}

    for heading in concentration_headings(soup):
        name = heading.get_text(" ", strip=True)
        details = scan_section(heading, name)

        if not details["required_courses"] and not details["approved_electives"]:
            credit_fallback(soup, name, details)

        print("Concentration:", name)
        print("Required courses:", len(details["required_courses"]))
        print("Approved electives:", len(details["approved_electives"]))

        check_details(name, details)
        ConcentrationRequirements(**details)
        results[name] = details

    expected = {heading.get_text(" ", strip=True) for heading in concentration_headings(soup)}

    missing = expected - set(results)

    if missing:
        raise ValueError( f"Missing Concentrations: {sorted(missing)}")

    return results


def save_json(data: dict, concentrations: dict) -> None:
    """I saved extracted course and concentration requirements to a JSON file."""

    if not data:
        raise ValueError ("No course data was found :(")

    missing = set(CATEGORIES) - set(data)

    if missing:
        raise ValueError(f"Missing Categories: {sorted(missing)}")

    root = Path(__file__).resolve().parents[1]

    output = root / "data" / "course_requirements.json"

    output.parent.mkdir(parents=True, exist_ok=True)

    dataset = {
        "source_url": URL, "categories": data, "concentrations": concentrations
    }

    with output.open("w", encoding="utf-8") as file:

        json.dump(dataset, file, indent=4, ensure_ascii=False)

    print("\nSaved JSON to:", output)


def main() -> None:
    """I run the web scraper and save the extracted degree requirements."""

    try:
        html = fetch_page(URL)
        soup = inspect_html(html)
        data = all_courses(soup)

        concentrations = extract_concentrations(soup)

        save_json(data, concentrations)

        print("\nYour scraping has been completed")

    except requests.RequestException as error:
        print("webiste request has failed:", error)
    
    except ValueError as error:
        print("There was an extraction:", error)
        
if __name__ == "__main__":
    main()
