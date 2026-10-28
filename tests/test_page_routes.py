from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
TEMPLATES = APP_DIR / "templates"
STATIC = APP_DIR / "static"


def test_page_templates_exist():
    pages = [
        "tiger_home.html",
        "tiger_schedule.html",
        "tiger_planner.html",
        "tiger_friends.html",
        "tiger_profile.html",
    ]
    for page in pages:
        assert (TEMPLATES / page).is_file(), f"Missing page: {page}"


def test_stylesheet_exists():
    assert (STATIC / "tiger_theme.css").is_file(), "Missing CSS file"


def test_homepage_loads_stylesheet():
    html = (TEMPLATES / "tiger_home.html").read_text()
    assert "tiger_theme.css" in html, "Homepage does not reference the CSS stylesheet"
