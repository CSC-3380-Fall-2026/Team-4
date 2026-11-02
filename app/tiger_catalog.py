"this is where the catalog enpoint will be"

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router: APIRouter= APIRouter()

DATA_FILE = ( Path(__file__).resolve().parents[1] / "data" / "course_requirements.json" )
REQUIRED_TEXT_FIELDS = ["course_code", "course_name", "category"]


def data_error(detail: str) -> HTTPException:
    # the 500 will indicate their is a problem with the saved data from the server.
    return HTTPException(status_code=500, detail=detail)


def load_courses() -> list[dict]:
    #This will return type list[dict] means the functions returns a list containing the dictionaries with one for each course 
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            # this will automatically close the file when the block ends and the r means read and the utf-8 is the specifics for it to understand the text and also it will convert the json contents to python.
            data = json.load(file)

    except FileNotFoundError:
        # Handles any missing course data and file raising the exception and wil stop  the 500 will indicate their is a problem with the saved data from the server.
        raise data_error("Their is course data missing. Add data/course_requirements.json.")

    except (json.JSONDecodeError, UnicodeDecodeError):
        # this will handle an invalid text or json syntax that cannont be read by the utf-8
        raise data_error("Invalid course data make sure its a JSON file.")

    except OSError:
        # This will handle other file errors not covered above like being able to read it
        raise data_error("The course data is unreadable please fix it")

    if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
        # this file will check whether a value is a a dictonary or catergorie if none it will return none if a key is missing
        raise data_error("Course data is missing categories.")

    courses = []

    for category, section in data["categories"].items():
        # this will if the name is empty will return that it is blank
        if not category.strip():
            raise data_error("This course category is blank please fix")

        if ( not isinstance(section, dict) or not isinstance(section.get("courses"), list)):
            # this will make sure each category contains a dictionary with the course list.
            raise data_error(f"Category '{category}' needs a new courses list.")

        # this will go through the individual courses and number starting at 1
        for number, course in enumerate(section["courses"], start=1):
            # this will create a label to indentify any errors that occurs with the courses
            location = f"Course {number} in '{category}'"

            if not isinstance(course, dict):
                # return an error if the course is not stored as a dictoniary
                raise data_error(f"{location} must be a object.")

            for field in REQUIRED_TEXT_FIELDS:
                # checks the course code name and category one at a time
                value = course.get(field)
                # will get the field value or none if it is missing

                if not isinstance(value, str) or not value.strip():
                    # return an eror if the value is blank or not text
                    raise data_error(f"{location} needs a nonempty text value for '{field}'.")

            credits = course.get("credits")
            # this will get the number of credit hours for the course:

            if type(credits) is not int or credits <= 0:
                # this will return a error if the credits are not a positive integer
                raise data_error(f"{location} needs a positive whole number for credits.")

            if course["category"].strip() != category.strip():
                # this will make sure the course category matches the section containing it
                raise data_error(f"{location} has a category that does not match its section.")

            # this will add the four required course fields and remove the surrounding spaces
            courses.append({
                "course_code": course["course_code"].strip(),
                "course_name": course["course_name"].strip(),
                "credits": credits,
                "category": course["category"].strip(),
            })

    return courses
    # will retuen the complete course list after verifying every record


@router.get("/courses", tags=["Course Catalog"])
def search_courses(query: str = "", category: str = "") -> list[dict]:
# this will create the endpoint under the catalog group and will load the saved courses and check to make sure the info is valid
    return filter_courses(load_courses(), query, category)


def filter_courses(courses: list[dict], query: str = "", category: str = "") -> list[dict]:
    query = query.strip().lower()
    category = category.strip().lower()
# this will remove the surrounding space and search text lowercase and category filter lowercase.
    matches = []
# this will check each course in the loaded list
    for course in courses:
        matches_search = (
            query == ""
            or query in course["course_code"].lower()
            or query in course["course_name"].lower()
          # this will match the text found or blank search in the course code or name
        )

        matches_category = (
            category == "" or category == course["category"].lower()
        )
# this will add the course to the results when they pass the checks
        if matches_search and matches_category:
            matches.append(course)
# will match the empty list if none or matching courseces if present
    return matches
