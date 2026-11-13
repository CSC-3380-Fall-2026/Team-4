"""Render William's shared navigation with project-relative template paths."""

from pathlib import Path
import secrets

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from lucide import lucide_icon
from markupsafe import Markup

APP_DIR: Path = Path(__file__).resolve().parent
CSRF_COOKIE: str = "tiger_csrf"
templates: Jinja2Templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)
NAV_LINKS: list[tuple[str, str, str]] = [
    ("Dashboard", "/dashboard", "layout-dashboard"),
    ("Schedule", "/schedule", "calendar"),
    ("Planning", "/planning", "bookmark"),
    ("Course Catalog", "/catalog", "search"),
    ("Friends", "/friends", "users"),
    ("Profile", "/profile", "user"),
]


def render_page(
    request: Request,
    template_name: str,
    status_code: int = 200,
    **context: object,
) -> HTMLResponse:
    """Render a page with shared navigation, icons, and a form token.

    Args:
        request: Current browser request.
        template_name: Exact template filename, including its capitalization.
        status_code: HTTP status for the rendered page.
        context: Page-specific values such as forms, results, and profile data.

    Returns:
        An uncached HTML response with the shared template context.
    """
    token: str = request.cookies.get(CSRF_COOKIE, "") or secrets.token_urlsafe(
        32
    )
    icons: dict[str, Markup] = {}
    for _, _, icon in NAV_LINKS:
        icons[icon] = Markup(lucide_icon(icon, width=18, height=18))
    page_context: dict[str, object] = {
        "nav_links": NAV_LINKS,
        "icons": icons,
        "csrf_token": token,
        "profile": None,
        "account_active": bool(request.cookies.get("tiger_access")),
    }
    page_context.update(context)
    response: HTMLResponse = templates.TemplateResponse(
        request=request,
        name=template_name,
        context=page_context,
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


def valid_token(request: Request, token: str) -> bool:
    """Check a browser form token before changing browser account state.

    Args:
        request: Request carrying the corresponding form-token cookie.
        token: Hidden token submitted with the form.

    Returns:
        Whether the nonempty submitted token matches the browser cookie.
    """
    expected: str = request.cookies.get(CSRF_COOKIE, "")
    return bool(
        expected
        and token
        and expected.isascii()
        and token.isascii()
        and secrets.compare_digest(expected, token)
    )
