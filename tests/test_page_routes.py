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


def test_expected_page_routes_registered():
    import ast

    source = (APP_DIR / "tiger_app.py").read_text()
    tree = ast.parse(source)

    routes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and node.args:
                if isinstance(node.args[0], ast.Constant):
                    routes.add(node.args[0].value)

    expected_routes = {
        "/": "Dashboard",
        "/schedule": "My Schedule",
        "/planning": "Planning",
        "/friends": "Friends",
        "/profile": "Profile",
        "/catalog": "Course Catalog",
    }

    missing = [
        f"{name} ({path})"
        for path, name in expected_routes.items()
        if path not in routes
    ]

    assert not missing, "Missing page routes: " + ", ".join(missing)


def test_homepage_navigation_has_links():
    from html.parser import HTMLParser

    class NavigationParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_nav = False
            self.links = []

        def handle_starttag(self, tag, attrs):
            if tag == "nav":
                self.in_nav = True
            elif tag == "a" and self.in_nav:
                self.links.append(dict(attrs).get("href"))

        def handle_endtag(self, tag):
            if tag == "nav":
                self.in_nav = False

    parser = NavigationParser()
    parser.feed((TEMPLATES / "tiger_home.html").read_text())

    assert parser.links, "Homepage navigation has no links"
    assert all(parser.links), "Homepage navigation contains links without href"
