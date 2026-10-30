#this is where the contents of the web scrapping will be for when we get course catalogs
import requests
import json
import re


from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString 
from pathlib import Path
from datetime import datetime, timezone

URL = "https://www.lsu.edu/eng/cse/programs/undergraduate_program/undergraduate_major.php"
DEBUG = True 
CATEGORIES = [ "Core Coursework", "Technical Requirements", "Math Requirements", "Other Requirements"]
STOP_HEADINGS = set(CATEGORIES + ["Concentrations"])

CONCENTRATIONS = ["Cloud Computing & Networking","Cybersecurity", "Data Science & Analytics", "Software Engineering", "Second Discipline"]

def fetch_page(url: str) -> str:
    print("we are fetching your webpage...")
    response = requests.get(url, timeout=15)

    response.raise_for_status()

    print("Status:", response.status_code)
    print("Characters:", len(response.text))
    return response.text 

def inspect_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr")
    print("\n Total table rows:", len(rows))

    if DEBUG:
        print("\n First 5 rows:")
        for row in rows[:5]:
            print(row.get_text(" ",strip=True))
    return soup

def find_categories(soup: BeautifulSoup) -> dict[str, Tag]:
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

def get_section_content(heading: Tag) -> tuple[list[Tag], list[str]]:
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

def extract_table_data(table: Tag, category: str) -> tuple[list[dict], list[dict]]:
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

def extract_all_courses(soup: BeautifulSoup) -> dict:
    headings = find_categories(soup)
    result: dict = {}
    for category in CATEGORIES:
        print("\nProcessing:", category)
        heading = headings[category]
        tables, notes = get_section_content(heading)
        courses: list[dict] = []
        requirements: list[dict] = []
        print("Tables have been found:", len(tables))

        for table in tables:
            found_courses, found_requiremnts = (extract_table_data(table, category))
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


def extract_concentrations(soup: BeautifulSoup) -> dict[str, dict]:
    results: dict[str, dict] = {}

    for heading  in soup.find_all(["h2","h3", "h4"]):
        name = " ".join(heading.get_text(" ", strip = True).replace ("\u200b", "").split())

        if name not in CONCENTRATIONS:
            continue
        details: dict = {"required_courses": [], "approved_electives": [], "other_requirements": [], "notes": []}

        section: str | None = None

        for element in heading.next_elements:
            if not isinstance(element, Tag):
                continue

            # Stop at the next concentration.
            if (element.name == ("h2", "h3", "h4") and element is not heading and " ".join (element.get_text(" ", strip=True).replace ("\u200b", "").split()) in CONCENTRATIONS):
                break

            if element.name == "footer":
                break

            # Stop at the bottom of the page.
            if element.name in ("a", "button"):
                if element.get_text(" ", strip=True) == "Top":
                    break

            # Identify required courses or electives.
            if element.name in ("h2", "h3", "h4"):
                title = element.get_text(" ", strip=True)

                section = {"Required Courses": "required_courses","Approved Electives": "approved_electives"}.get(title)

            # Extract course information.
            elif element.name == "table" and section is not None:
                courses, requirements = extract_table_data(element, f"{name} - {section.replace('_', ' ')}")

                details[section].extend(courses)
                details["other_requirements"].extend(requirements)

            # Extract additional written information.
            elif element.name == "p":
                if element.find_parent("table") is None:
                    note = element.get_text(" ", strip=True)

                    if note:
                        details["notes"].append(note)


        print("Concentration:", name)
        print("Required courses:", len(details["required_courses"]))
        print("Approved electives:", len(details["approved_electives"]))

        # Validate course extraction.
        if name != "Second Discipline":
            if (not details["required_courses"] or not details["approved_electives"]):
                raise ValueError(f"Incomplete course lists for {name}")

        results[name] = details

    if "Second Discipline" not in results:
        page_text = " ".join(
            soup.get_text(" ", strip=True).split()
        )

        requirement = re.search( r"Students\s+must\s+complete\s+a\s+total\s+of\s+" r"15\s+credit\s+hours\b.{0,300}?\.", page_text, re.IGNORECASE)

        approval = re.search( r"This\s+concentration\s+must\s+be\s+approved\s+" r"by\s+a\s+departmental\s+advisor\.", page_text, re.IGNORECASE)

        if requirement is None:
            raise ValueError("Second Discipline requirement not found")

        notes = [requirement.group(0)]

        if approval:
            notes.append(approval.group(0))

        results["Second Discipline"] = {
            "required_courses": [],
            "approved_electives": [],
            "other_requirements": [],
            "notes": notes,
            "required_credit_hours": 15
        }

        print("Concentration: Second Discipline")
        print("Required credit hours: 15")

    missing = set(CONCENTRATIONS) - set(results)

    if missing:
        raise ValueError( f"Missing Concentrations: {sorted(missing)}")

    return results


def save_json(data: dict, concentrations: dict) -> None:

    if not data:
        raise ValueError ("No course data was found :(")

    missing = set(CATEGORIES) - set(data)

    if missing:
        raise ValueError(f"Missing Categories: {sorted(missing)}")

    root = Path(__file__).resolve().parents[1]

    output = root / "data" / "course_requirements.json"

    output.parent.mkdir(parents = True, exist_ok = True)

    dataset = {
        "source_url": URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "categories": data, "concentrations": concentrations
    }

    with output.open("w", encoding = "utf-8") as file:
        json.dump(dataset, file, indent = 4, ensure_ascii = False)

    print("\nSaved JSON to:", output)


def main() -> None:
    try:
        html = fetch_page(URL)
        soup = inspect_html(html)
        data = extract_all_courses(soup)

        concentrations = extract_concentrations(soup)

        save_json(data, concentrations)

        print("\nYour scraping has been completed")

    except requests.RequestException as error:
        print("webiste request has failed:", error)
    
    except ValueError as error:
        print("There was an extraction:", error)
        

if __name__ == "__main__":
    main()
