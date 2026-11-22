import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import tiger_catalog


SAMPLE_COURSES = [
    {"course_code": "CSC 1350", "course_name": "Computer Science I", "credits": 3, "category": "Core"},
    {"course_code": "CSC 3380", "course_name": "Software Engineering", "credits": 3, "category": "Core"},
    {"course_code": "MATH 1550", "course_name": "Calculus I", "credits": 5, "category": "Math"},
]


def test_catalog_search_by_course_code(monkeypatch):
    monkeypatch.setattr(tiger_catalog, "load_courses", lambda: SAMPLE_COURSES)
    results = tiger_catalog.search_courses(query="CSC 3380")
    assert [course["course_code"] for course in results] == ["CSC 3380"]


def test_catalog_search_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(tiger_catalog, "load_courses", lambda: SAMPLE_COURSES)
    results = tiger_catalog.search_courses(query="software")
    assert [course["course_code"] for course in results] == ["CSC 3380"]


def test_catalog_filter_by_category(monkeypatch):
    monkeypatch.setattr(tiger_catalog, "load_courses", lambda: SAMPLE_COURSES)
    results = tiger_catalog.search_courses(category="Math")
    assert [course["course_code"] for course in results] == ["MATH 1550"]


def test_catalog_combined_search_and_filter(monkeypatch):
    monkeypatch.setattr(tiger_catalog, "load_courses", lambda: SAMPLE_COURSES)
    results = tiger_catalog.search_courses(query="CSC", category="Math")
    assert results == []
