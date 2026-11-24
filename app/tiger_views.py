"""Render William's shared navigation with project-relative template paths."""

from collections.abc import Mapping
from pathlib import Path
import secrets

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
        "search": icons["search"],
        "plus": Markup(lucide_icon("plus", width=18, height=18)),
        "csrf_token": token,
        "profile": None,
        "account_active": bool(
            request.cookies.get("tiger_access")
            or request.cookies.get("tiger_refresh")
        ),
    }
    page_context.update(context)
    response: HTMLResponse = templates.TemplateResponse(
        request=request,
        name=template_name,
        context=page_context,
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    set_cookie(response, request, CSRF_COOKIE, token)
    return response


def set_cookie(
    response: Response,
    request: Request,
    name: str,
    value: str,
    max_age: int | None = None,
) -> None:
    """Set an HTTP-only, same-site cookie, secure whenever the site is HTTPS.

    Args:
        response: Response that carries the cookie.
        request: Current request, used to detect HTTPS, directly or
            through a proxy's X-Forwarded-Proto header.
        name: Cookie name.
        value: Cookie value.
        max_age: Lifetime in seconds, or None for a browser-session cookie.
    """
    # Vercel ends HTTPS at its proxy, so the app may only see http.
    forwarded: str | None = request.headers.get("x-forwarded-proto")
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure="https" in (request.url.scheme, forwarded),
        samesite="lax",
    )


def redirect_to(url: str) -> RedirectResponse:
    """Redirect a form or page request without letting the browser cache it.

    Args:
        url: Address to send the browser to.

    Returns:
        An uncached 303 redirect.
    """
    response: RedirectResponse = RedirectResponse(url, status_code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


def valid_token(request: Request, form: Mapping[str, object]) -> bool:
    """Check a submitted form's token before changing browser account state.

    Args:
        request: Request carrying the corresponding form-token cookie.
        form: Submitted form fields, including the hidden csrf_token.

    Returns:
        Whether the nonempty submitted token matches the browser cookie.
    """
    token: str = str(form.get("csrf_token", ""))
    expected: str = request.cookies.get(CSRF_COOKIE, "")
    return bool(
        expected
        and token
        and expected.isascii()
        and token.isascii()
        and secrets.compare_digest(expected, token)
    )
