#this is where the contents of the web scrapping will be for when we get course catalogs
import requests
import json
import re


from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timezone

URL = "https://www.lsu.edu/eng/cse/programs/undergraduate_program/undergraduate_major.php"

DEBUG = True 

def fetch_page(url):
    
    print("we are fetching your webpage...")
    
    response = requests.get(url, timeout=15)

    
    response.raise_for_status()

    print("Status:", response.status_code)
    print("Characters:", len(response.text))

    return response.text 

def inspect_html(html):

    soup = BeautifulSoup(html, "html.parser")

    rows = soup.select("tr")

    print("\n Total table rows:", len(rows))

    if DEBUG:

        print("\n First 5 rows:")

        for row in rows[:5]:
            print(row.get_text(" ",strip=True))

def extract_courses(soup):

    courses = []
    seen = set()

    rows = soup.select("tr")

    for row in rows:
        cells = row.find_all(["td", "th"])

        if len(cells) < 3:
            continue

        code = cells[0].get_text(" ", strip=True)
        name = cells[1].get_text(" ", strip=True)
        credits = cells[2].get_text(" ", strip=True)

        if not re.fullmatch(r"CSC\s+\d{4}", code):
            continue

        if not credits.isdigit():
            if DEBUG:
                print("Skipping the invalid contents:", code)
            continue

        if code in seen:
            continue

        seen.add(code)

        course = {
            "id": code.lower().replace(" ", "-"),
            "course_code": code,
            "course_name": name,
            "credits": int(credits),
            "source_url": URL
        }

        courses.append(course)

        if DEBUG:
            print("Extracted:", course)

    return courses


def save_json(courses):

    if not courses:
        raise ValueError("No courses were found. Check the HTML selector.")

    data = {
        "retrieved at": datetime.now(timezone.utc).isoformat(),
        "courses": courses
    }

    root = Path(__file__).resolve().parents[1]
    output = root / "data" / "scrapped_course.json"

    output.parent.mkdir(exist_ok=True)

    with output.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    print("\nSaved JSON to:", output)
    return output


def main():

    html = fetch_page(URL)
    soup = inspect_html(html)
    courses = extract_courses(soup)

    print("\nTotal courses extracted:", len(courses))
    save_json(courses)
    return courses


if __name__ == "__main__":
    main()
